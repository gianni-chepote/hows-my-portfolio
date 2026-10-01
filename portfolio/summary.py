"""Templated summary built only from engine outputs.

Describes the portfolio; never recommends trades. Every number in the text is
read from `Exposure` / `CorrResult`, and `Summary.numbers` records each one so
tests can check the text against the engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from portfolio.correlation import CorrResult, top_pair
from portfolio.data import Issue
from portfolio.exposure import UNCLASSIFIED_EQUITY, UNKNOWN, Exposure

# Thresholds for what the summary mentions.
HIDDEN_MIN_TOTAL = 0.05    # company exposure worth mentioning
HIDDEN_MULTIPLE = 1.5      # total / direct above this = mostly held through funds
NEAR_DUPLICATE = 0.95      # asset pair moving almost as one
GAP_FLAG = 0.005           # unknown share worth disclosing


def pct(x: float) -> str:
    return f"{x:.1%}"


def rho(x: float) -> str:
    return f"{x:.2f}"


@dataclass
class Point:
    kind: str   # "position" | "sector" | "company" | "correlation" | "concentration" | "coverage"
    text: str


@dataclass
class Summary:
    headline: str
    points: list[Point]
    numbers: dict[str, str] = field(default_factory=dict)  # label -> formatted value used in text

    @property
    def text(self) -> str:
        return "\n".join([self.headline, *(f"- {p.text}" for p in self.points)])


def build_summary(
    ex: Exposure,
    assets: CorrResult,
    sectors: CorrResult,
    issues: list[Issue] | None = None,
) -> Summary:
    n: dict[str, str] = {}
    c = ex.concentration
    points: list[Point] = []

    n["total_value"] = f"${ex.total_value:,.0f}"
    n["n_positions"] = str(c["n_positions"])
    n["effective_positions"] = f"{c['effective_positions']:.1f}"
    positions_word = "position" if c["n_positions"] == 1 else "positions"
    headline = (
        f"{n['n_positions']} {positions_word} worth {n['total_value']}. By weight, they are equivalent to "
        f"{n['effective_positions']} equal-sized positions."
    )

    # Largest position.
    n["largest_position_weight"] = pct(c["largest_position_weight"])
    text = f"The largest position is {c['largest_position']} at {n['largest_position_weight']} of the portfolio."
    points.append(Point("position", text))

    # Largest sector.
    if c["largest_sector"]:
        n["largest_sector_weight"] = pct(c["largest_sector_weight"])
        text = (
            f"The largest sector exposure is {c['largest_sector']} at {n['largest_sector_weight']}, "
            "after looking through the funds."
        )
        points.append(Point("sector", text))

    # Companies held mostly through funds.
    co = ex.companies
    if not co.empty:
        direct = co["direct"] if "direct" in co else 0.0
        hidden = co[(co["total"] >= HIDDEN_MIN_TOTAL) & (co["total"] > HIDDEN_MULTIPLE * direct)]
        for i, row in enumerate(hidden.head(2).itertuples(index=False)):
            d = float(getattr(row, "direct", 0.0))
            n[f"company_{i}_total"] = pct(row.total)
            funds = row.n_sources - (1 if d > 0 else 0)
            fund_word = "fund" if funds == 1 else "funds"
            n[f"company_{i}_funds"] = str(funds)
            if d > 0:
                n[f"company_{i}_direct"] = pct(d)
                text = (
                    f"{row.symbol} is {n[f'company_{i}_direct']} held directly but {n[f'company_{i}_total']} "
                    f"in total, because {funds} {fund_word} also hold it."
                )
            else:
                text = (
                    f"{row.symbol} is not held directly but is {n[f'company_{i}_total']} of the portfolio "
                    f"through {funds} {fund_word}."
                )
            points.append(Point("company", text))

    # Correlations.
    pair = top_pair(assets)
    if not assets.ok:
        points.append(Point("correlation", "Asset correlations need at least two holdings with enough price history."))
    elif pair is None:
        points.append(Point("correlation", "No two holdings had a positive return correlation over the window."))
    else:
        a, b, r = pair
        n["asset_pair_rho"] = rho(r)
        text = f"{a} and {b} are the most correlated holdings ({n['asset_pair_rho']} over the past year)."
        if r >= NEAR_DUPLICATE:
            text += " Their daily returns move almost as one."
        points.append(Point("correlation", text))

    spair = top_pair(sectors)
    if spair is not None:
        a, b, r = spair
        n["sector_pair_rho"] = rho(r)
        points.append(Point(
            "correlation",
            f"Among the sectors held, {a} and {b} are the most correlated ({n['sector_pair_rho']}, "
            "measured with SPDR sector ETFs).",
        ))
    elif sectors.ok:
        points.append(Point("correlation", "No two held sectors had a positive return correlation over the window."))

    # Coverage and data gaps.
    sec = ex.sectors.set_index("bucket")["weight"]
    unknown = float(sec[UNKNOWN]) + float(sec[UNCLASSIFIED_EQUITY])
    if unknown > GAP_FLAG:
        n["unknown_share"] = pct(unknown)
        points.append(Point(
            "coverage", f"{n['unknown_share']} of the portfolio has no asset-class or sector data and is shown as unknown."
        ))
    named = ex.coverage["equity_named"]
    if named is not None and named < 0.999 and ex.coverage["equity_undisclosed"] > GAP_FLAG:
        n["equity_named"] = pct(named)
        points.append(Point(
            "coverage",
            f"Company-level figures cover {n['equity_named']} of the equity exposure; the data source lists only "
            "each fund's top 10 holdings.",
        ))
    excluded = sorted(set(assets.excluded) | set(sectors.excluded))
    if excluded:
        points.append(Point("coverage", f"Left out of the correlations for lack of data: {', '.join(excluded)}."))
    dropped = [i.ticker for i in (issues or []) if i.level == "error" and i.ticker]
    if dropped:
        points.append(Point("coverage", f"Not included anywhere: {', '.join(dropped)} (see the warnings above)."))

    return Summary(headline, points, n)
