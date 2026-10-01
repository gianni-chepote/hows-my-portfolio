"""Step 2: freeze a yfinance snapshot of the test portfolio and sector proxies.

Run from the repo root:
    ./.venv/bin/python fins2026/hows-my-portfolio/scratch/02_fixtures.py

Writes to fixtures/:
    quotes.json        latest price, currency, timestamp, type, sector, category
    funds.json         ETF sector weights, asset classes, top holdings
    prices_1y.parquet  adjusted daily closes, one column per ticker
    README.md          pull date and contents
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "fixtures"

TEST_PORTFOLIO = ["SPY", "VOO", "QQQ", "AAPL", "NVDA", "IBIT", "JPM"]
SECTOR_PROXIES = ["XLK", "XLF", "XLV", "XLY", "XLC", "XLI", "XLE", "XLB", "XLP", "XLU", "XLRE"]
QUOTE_FIELDS = [
    "quoteType", "shortName", "longName", "regularMarketPrice", "currency",
    "regularMarketTime", "sector", "industry", "category",
]


def pull_quote(t: yf.Ticker) -> dict:
    info = t.info
    return {k: info.get(k) for k in QUOTE_FIELDS}


def pull_fund(t: yf.Ticker) -> dict:
    fd = t.funds_data
    th = fd.top_holdings
    holdings = []
    if isinstance(th, pd.DataFrame) and not th.empty:
        for symbol, row in th.iterrows():
            holdings.append(
                {"symbol": str(symbol), "name": row.get("Name"), "weight": float(row["Holding Percent"])}
            )
    return {
        "sector_weightings": {k: float(v) for k, v in (fd.sector_weightings or {}).items()},
        "asset_classes": {k: float(v) for k, v in (fd.asset_classes or {}).items()},
        "top_holdings": holdings,
    }


def main() -> None:
    OUT.mkdir(exist_ok=True)
    symbols = TEST_PORTFOLIO + SECTOR_PROXIES

    quotes, funds = {}, {}
    for s in symbols:
        t = yf.Ticker(s)
        quotes[s] = pull_quote(t)
        if s in TEST_PORTFOLIO and quotes[s]["quoteType"] == "ETF":
            funds[s] = pull_fund(t)
        print(f"pulled {s}")

    prices = yf.download(symbols, period="1y", auto_adjust=True, progress=False)["Close"]
    prices = prices[symbols]
    prices.index = pd.to_datetime(prices.index).tz_localize(None)
    prices.index.name = "date"

    (OUT / "quotes.json").write_text(json.dumps(quotes, indent=2))
    (OUT / "funds.json").write_text(json.dumps(funds, indent=2))
    prices.to_parquet(OUT / "prices_1y.parquet")

    pulled = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    (OUT / "README.md").write_text(
        "# Fixtures\n\n"
        f"Pulled {pulled} with yfinance {yf.__version__} by `scratch/02_fixtures.py`.\n"
        "Frozen snapshot for offline tests. Re-run the script to refresh.\n\n"
        "| File | Contents |\n|---|---|\n"
        f"| `quotes.json` | {', '.join(QUOTE_FIELDS)} for {len(symbols)} tickers |\n"
        f"| `funds.json` | sector weights, asset classes, top-10 holdings for {', '.join(funds)} |\n"
        f"| `prices_1y.parquet` | adjusted daily closes, {prices.index.min().date()} to "
        f"{prices.index.max().date()}, {len(prices)} rows × {prices.shape[1]} tickers |\n\n"
        f"Tickers: test portfolio {', '.join(TEST_PORTFOLIO)}; sector proxies {', '.join(SECTOR_PROXIES)}.\n"
    )
    print(f"wrote fixtures to {OUT}")


if __name__ == "__main__":
    main()
