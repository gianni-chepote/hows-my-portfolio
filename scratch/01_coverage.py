"""Step 1: check what yfinance returns for the test portfolio and sector proxies.

Run from the repo root:
    ./.venv/bin/python "fins2026/hows-my-portfolio/scratch/01_coverage.py"

Writes scratch/coverage_report.md and scratch/coverage_raw.json.
"""

from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

HERE = Path(__file__).resolve().parent
TEST_PORTFOLIO = {"SPY": 20, "VOO": 10, "QQQ": 15, "AAPL": 10, "NVDA": 5, "IBIT": 20, "JPM": 8}
SECTOR_PROXIES = {
    "XLK": "Technology", "XLF": "Financials", "XLV": "Healthcare",
    "XLY": "Consumer Discretionary", "XLC": "Communication Services",
    "XLI": "Industrials", "XLE": "Energy", "XLB": "Materials",
    "XLP": "Consumer Staples", "XLU": "Utilities", "XLRE": "Real Estate",
}


def safe(fn):
    try:
        return fn(), None
    except Exception as exc:  # noqa: BLE001 - spike: record every failure
        return None, f"{type(exc).__name__}: {exc}"


def probe(symbol: str) -> dict:
    t = yf.Ticker(symbol)
    row: dict = {"symbol": symbol, "errors": {}}

    info, err = safe(lambda: t.info)
    if err:
        row["errors"]["info"] = err
    info = info or {}
    row["quote_type"] = info.get("quoteType")
    row["name"] = info.get("shortName") or info.get("longName")
    row["price"] = info.get("regularMarketPrice") or info.get("currentPrice")
    row["currency"] = info.get("currency")
    ts = info.get("regularMarketTime")
    row["price_time_utc"] = (
        datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if isinstance(ts, (int, float)) else ts
    )
    row["delay_min"] = info.get("exchangeDataDelayedBy")
    row["market_state"] = info.get("marketState")
    row["sector"] = info.get("sector")
    row["category"] = info.get("category")  # fund category, e.g. "Digital Assets"

    hist, err = safe(lambda: t.history(period="1y", auto_adjust=True))
    if err:
        row["errors"]["history"] = err
    if hist is not None and not hist.empty:
        row["hist_obs"] = int(hist["Close"].notna().sum())
        row["hist_start"] = str(hist.index.min().date())
        row["hist_end"] = str(hist.index.max().date())
    else:
        row["hist_obs"] = 0

    if row["quote_type"] == "ETF":
        fd = t.funds_data
        sw, err = safe(lambda: fd.sector_weightings)
        if err:
            row["errors"]["sector_weightings"] = err
        row["sector_weightings"] = sw or {}
        row["sector_weight_sum"] = round(sum(sw.values()), 4) if sw else None

        ac, err = safe(lambda: fd.asset_classes)
        if err:
            row["errors"]["asset_classes"] = err
        row["asset_classes"] = ac or {}

        th, err = safe(lambda: fd.top_holdings)
        if err:
            row["errors"]["top_holdings"] = err
        if isinstance(th, pd.DataFrame) and not th.empty:
            pct_col = next((c for c in th.columns if "percent" in c.lower()), None)
            row["top_holdings"] = {
                str(idx): float(th.loc[idx, pct_col]) if pct_col else None for idx in th.index
            }
            row["top_holdings_n"] = len(th)
            row["top_holdings_cover"] = round(float(th[pct_col].sum()), 4) if pct_col else None
        else:
            row["top_holdings"] = {}
            row["top_holdings_n"] = 0
            row["top_holdings_cover"] = None
    return row


def fmt(x, pct=False):
    if x is None or x == {} or (isinstance(x, float) and pd.isna(x)):
        return "—"
    if pct:
        return f"{x:.1%}"
    return str(x)


def main() -> None:
    symbols = list(TEST_PORTFOLIO) + list(SECTOR_PROXIES)
    rows = []
    for s in symbols:
        try:
            rows.append(probe(s))
        except Exception:  # noqa: BLE001
            rows.append({"symbol": s, "errors": {"probe": traceback.format_exc(limit=1)}})
        print(f"probed {s}")

    (HERE / "coverage_raw.json").write_text(json.dumps(rows, indent=2, default=str))

    pulled = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Step 1 — yfinance coverage report",
        "",
        f"Pulled {pulled} with yfinance {yf.__version__}. Raw output: `coverage_raw.json`.",
        "",
        "## Test portfolio — basics",
        "",
        "| Ticker | Type | Name | Price | Ccy | Price time (UTC) | Delay (min) | Sector / category | 1y obs |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    by_sym = {r["symbol"]: r for r in rows}
    for s in TEST_PORTFOLIO:
        r = by_sym[s]
        lines.append(
            f"| {s} | {fmt(r.get('quote_type'))} | {fmt(r.get('name'))} | {fmt(r.get('price'))} | "
            f"{fmt(r.get('currency'))} | {fmt(r.get('price_time_utc'))} | {fmt(r.get('delay_min'))} | "
            f"{fmt(r.get('sector') or r.get('category'))} | {fmt(r.get('hist_obs'))} |"
        )

    lines += [
        "",
        "## Test portfolio — ETF look-through data",
        "",
        "| ETF | Sector weights (n / sum) | Asset classes | Top holdings (n / % of fund) |",
        "|---|---|---|---|",
    ]
    for s in TEST_PORTFOLIO:
        r = by_sym[s]
        if r.get("quote_type") != "ETF":
            continue
        sw = r.get("sector_weightings") or {}
        ac = {k: round(v, 4) for k, v in (r.get("asset_classes") or {}).items() if v}
        lines.append(
            f"| {s} | {len(sw)} / {fmt(r.get('sector_weight_sum'), pct=True)} | {fmt(ac)} | "
            f"{r.get('top_holdings_n', 0)} / {fmt(r.get('top_holdings_cover'), pct=True)} |"
        )

    lines += ["", "### Top holdings detail", ""]
    for s in TEST_PORTFOLIO:
        r = by_sym[s]
        if r.get("top_holdings"):
            items = ", ".join(f"{k} {v:.1%}" for k, v in r["top_holdings"].items())
            lines.append(f"- **{s}**: {items}")

    lines += ["", "### Sector-weight keys returned (SPY)", ""]
    lines.append(f"`{list((by_sym['SPY'].get('sector_weightings') or {}).keys())}`")

    lines += [
        "",
        "## Sector proxies (SPDR)",
        "",
        "| Ticker | Sector | Price | 1y obs | History range |",
        "|---|---|---|---|---|",
    ]
    for s, name in SECTOR_PROXIES.items():
        r = by_sym[s]
        rng = f"{r.get('hist_start', '—')} → {r.get('hist_end', '—')}"
        lines.append(f"| {s} | {name} | {fmt(r.get('price'))} | {fmt(r.get('hist_obs'))} | {rng} |")

    errs = [(r["symbol"], k, v) for r in rows for k, v in r.get("errors", {}).items()]
    lines += ["", "## Errors", ""]
    lines += [f"- {s} `{k}`: {v}" for s, k, v in errs] or ["None."]

    (HERE / "coverage_report.md").write_text("\n".join(lines) + "\n")
    print("wrote coverage_report.md")


if __name__ == "__main__":
    main()
