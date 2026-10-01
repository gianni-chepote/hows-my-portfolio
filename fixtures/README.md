# Fixtures

Pulled 2026-09-30 08:47 UTC with yfinance 1.4.1 by `scratch/02_fixtures.py`.
Frozen snapshot for offline tests. Re-run the script to refresh.

| File | Contents |
|---|---|
| `quotes.json` | quoteType, shortName, longName, regularMarketPrice, currency, regularMarketTime, sector, industry, category for 18 tickers |
| `funds.json` | sector weights, asset classes, top-10 holdings for SPY, VOO, QQQ, IBIT |
| `prices_1y.parquet` | adjusted daily closes, 2025-09-30 to 2026-09-29, 251 rows × 18 tickers |

Tickers: test portfolio SPY, VOO, QQQ, AAPL, NVDA, IBIT, JPM; sector proxies XLK, XLF, XLV, XLY, XLC, XLI, XLE, XLB, XLP, XLU, XLRE.
