"""Exposure engine: positions, asset classes, sectors, underlying companies.

Two views are kept apart (brief, "Methodology rules"):
- purchased positions: what the user bought, one row per ticker;
- underlying exposure: what those positions hold, with ETFs looked through.
A fund's value is never added on top of its constituents.

All weights are fractions of total portfolio value (0.08 = 8%).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from portfolio.data import SECTORS, MarketData, canonical_symbol

EQUITY, FIXED_INCOME, CASH = "Equity", "Fixed income", "Cash"
COMMODITIES, CRYPTO, OTHER, UNKNOWN = "Commodities", "Crypto", "Other", "Unknown"
ASSET_CLASSES = [EQUITY, FIXED_INCOME, CASH, COMMODITIES, CRYPTO, OTHER, UNKNOWN]

UNCLASSIFIED_EQUITY = "Unclassified equity"
OTHER_HOLDINGS = "Other holdings (not disclosed)"

# yfinance fund asset-class keys -> our buckets.
_FUND_ASSET_MAP = {
    "stockPosition": EQUITY,
    "bondPosition": FIXED_INCOME,
    "cashPosition": CASH,
    "preferredPosition": OTHER,
    "convertiblePosition": OTHER,
    "otherPosition": OTHER,
}

_TOL = 1e-9


def _fund_override(category: str | None) -> str | None:
    """Fund categories that pin the whole fund to one asset class."""
    if not category:
        return None
    if category == "Digital Assets":
        return CRYPTO
    if "commodit" in category.lower():
        return COMMODITIES
    return None


@dataclass
class Exposure:
    total_value: float
    positions: pd.DataFrame       # purchased view
    asset_classes: pd.DataFrame   # asset_class, weight, value
    sectors: pd.DataFrame         # bucket, kind, weight, value
    companies: pd.DataFrame       # underlying companies, direct + via funds
    fund_split: pd.DataFrame      # per fund: equity weight, named, undisclosed
    coverage: dict
    concentration: dict


def compute_exposure(md: MarketData) -> Exposure:
    if md.quotes.empty:
        raise ValueError("No priced holdings to analyse.")

    positions = _positions(md)
    total = float(positions["value"].sum())
    fund_split = _fund_split(md, positions)
    asset_classes = _asset_classes(positions, fund_split, total)
    sectors = _sectors(md, positions, asset_classes, total)
    companies = _companies(md, positions, total)
    coverage = _coverage(asset_classes, sectors, companies, fund_split)
    concentration = _concentration(positions, sectors, companies)
    return Exposure(total, positions, asset_classes, sectors, companies, fund_split, coverage, concentration)


# --------------------------------------------------------------------------- purchased view


def _positions(md: MarketData) -> pd.DataFrame:
    p = md.quotes.copy()
    p["value"] = p["shares"] * p["price"]
    p["weight"] = p["value"] / p["value"].sum()
    p["wrapper"] = p["quote_type"].map({"EQUITY": "Stock", "ETF": "ETF"})
    cols = ["ticker", "name", "wrapper", "shares", "price", "value", "weight", "sector", "category"]
    return p[cols].sort_values("value", ascending=False, ignore_index=True)


# --------------------------------------------------------------------------- asset classes


def _fund_split(md: MarketData, positions: pd.DataFrame) -> pd.DataFrame:
    """One row per (position, asset class) as a share of that position.

    Stocks are 100% equity. Funds use their asset-class split; a category
    override (crypto, commodities) wins; any residual or missing data is Unknown.
    """
    assets = md.fund_assets.groupby("fund")
    rows = []
    for pos in positions.itertuples(index=False):
        if pos.wrapper == "Stock":
            rows.append((pos.ticker, EQUITY, 1.0))
            continue
        override = _fund_override(pos.category)
        if override:
            rows.append((pos.ticker, override, 1.0))
            continue
        if pos.ticker not in assets.groups:
            rows.append((pos.ticker, UNKNOWN, 1.0))
            continue
        split = assets.get_group(pos.ticker)
        mapped = split.assign(asset_class=split["asset_class"].map(_FUND_ASSET_MAP).fillna(OTHER))
        mapped = mapped.groupby("asset_class")["weight"].sum()
        for cls, w in mapped.items():
            if w > _TOL:
                rows.append((pos.ticker, cls, float(w)))
        residual = 1.0 - float(mapped.sum())
        if residual > _TOL:
            rows.append((pos.ticker, UNKNOWN, residual))
    split = pd.DataFrame(rows, columns=["ticker", "asset_class", "share"])
    w = positions.set_index("ticker")["weight"]
    split["weight"] = split["share"] * split["ticker"].map(w)
    return split


def _asset_classes(positions, fund_split, total) -> pd.DataFrame:
    ac = fund_split.groupby("asset_class")["weight"].sum().reindex(ASSET_CLASSES, fill_value=0.0)
    out = ac.rename("weight").rename_axis("asset_class").reset_index()
    out["value"] = out["weight"] * total
    return out


# --------------------------------------------------------------------------- sectors


def _sectors(md, positions, asset_classes, total) -> pd.DataFrame:
    """GICS sectors for the equity part; every other asset class as its own bucket.

    Equity that cannot be placed in a sector is 'Unclassified equity', so the
    table always sums to 100% of the portfolio.
    """
    w = positions.set_index("ticker")["weight"]
    equity_share = asset_classes.set_index("asset_class")["weight"]

    contrib = {s: 0.0 for s in SECTORS}
    # Direct stocks.
    for pos in positions.itertuples(index=False):
        if pos.wrapper == "Stock" and isinstance(pos.sector, str):
            contrib[pos.sector] += pos.weight
    # Funds: one route only — provider sector weights, scaled by the equity sleeve.
    stock_pos = md.fund_assets.query("asset_class == 'stockPosition'").set_index("fund")["weight"]
    for fund, grp in md.fund_sectors.dropna(subset=["sector"]).groupby("fund"):
        if fund not in w.index or _fund_override(positions.set_index("ticker").at[fund, "category"]):
            continue
        sleeve = w[fund] * float(stock_pos.get(fund, 0.0))
        for sector, sw in grp.groupby("sector")["weight"].sum().items():
            contrib[sector] += sleeve * sw

    rows = [(s, "sector", v) for s, v in contrib.items()]
    unclassified = equity_share[EQUITY] - sum(contrib.values())
    rows.append((UNCLASSIFIED_EQUITY, "unclassified", max(unclassified, 0.0)))
    for cls in ASSET_CLASSES[1:]:
        rows.append((cls, "unknown" if cls == UNKNOWN else "non-equity", float(equity_share[cls])))
    out = pd.DataFrame(rows, columns=["bucket", "kind", "weight"])
    out["value"] = out["weight"] * total
    return out


# --------------------------------------------------------------------------- underlying companies


def _companies(md, positions, total) -> pd.DataFrame:
    """Direct stock plus look-through ownership, one row per company.

    Columns: symbol, name, direct, via_<FUND> per fund, total, n_sources,
    value. Only disclosed fund holdings (top 10) appear; the rest of each
    fund is summarised in `fund_split`/coverage as undisclosed.
    """
    w = positions.set_index("ticker")["weight"]
    rows = []
    for pos in positions.itertuples(index=False):
        if pos.wrapper == "Stock":
            rows.append((canonical_symbol(pos.ticker), pos.name, "direct", pos.weight))
    for h in md.fund_holdings.itertuples(index=False):
        if h.fund in w.index:
            rows.append((h.symbol, h.name, f"via {h.fund}", w[h.fund] * h.weight))
    if not rows:
        return pd.DataFrame(columns=["symbol", "name", "total", "n_sources", "value"])

    long = pd.DataFrame(rows, columns=["symbol", "name", "source", "weight"])
    names = long.drop_duplicates("symbol").set_index("symbol")["name"]  # direct names come first
    wide = long.pivot_table(index="symbol", columns="source", values="weight", aggfunc="sum", fill_value=0.0)
    source_cols = (["direct"] if "direct" in wide else []) + sorted(c for c in wide if c != "direct")
    wide = wide[source_cols]
    wide["total"] = wide.sum(axis=1)
    wide["n_sources"] = (wide[source_cols] > 0).sum(axis=1)
    wide.insert(0, "name", names)
    wide["value"] = wide["total"] * total
    return wide.sort_values("total", ascending=False).reset_index()


# --------------------------------------------------------------------------- coverage & concentration


def _coverage(asset_classes, sectors, companies, fund_split) -> dict:
    ac = asset_classes.set_index("asset_class")["weight"]
    sec = sectors.set_index("bucket")["weight"]
    equity = float(ac[EQUITY])
    named = float(companies["total"].sum()) if not companies.empty else 0.0
    return {
        # Share of portfolio value whose asset class is known.
        "asset_class_known": 1.0 - float(ac[UNKNOWN]),
        # Share of portfolio value placed in a sector or a known non-equity bucket.
        "sector_known": 1.0 - float(sec[UNKNOWN]) - float(sec[UNCLASSIFIED_EQUITY]),
        # Share of equity exposure attributed to named companies.
        "equity_named": named / equity if equity > _TOL else None,
        "equity_undisclosed": max(equity - named, 0.0),
    }


def _concentration(positions, sectors, companies) -> dict:
    w = positions["weight"]
    hhi = float((w**2).sum())
    equity_sectors = sectors.query("kind == 'sector' and weight > 0")
    top_sector = equity_sectors.sort_values("weight", ascending=False).head(1)
    top_co = companies.head(1)
    return {
        "n_positions": int(len(positions)),
        "largest_position": positions.at[0, "ticker"],
        "largest_position_weight": float(w.iloc[0]),
        "top5_positions_weight": float(w.head(5).sum()),
        "hhi": hhi,
        "effective_positions": 1.0 / hhi,
        "largest_sector": top_sector["bucket"].iloc[0] if not top_sector.empty else None,
        "largest_sector_weight": float(top_sector["weight"].iloc[0]) if not top_sector.empty else 0.0,
        "largest_company": top_co["symbol"].iloc[0] if not top_co.empty else None,
        "largest_company_weight": float(top_co["total"].iloc[0]) if not top_co.empty else 0.0,
        "top5_companies_weight": float(companies["total"].head(5).sum()) if not companies.empty else 0.0,
    }
