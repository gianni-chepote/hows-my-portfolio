# Step 1 — yfinance coverage report

Pulled 2026-09-30 08:41 UTC with yfinance 1.4.1. Raw output: `coverage_raw.json`.

## Test portfolio — basics

| Ticker | Type | Name | Price | Ccy | Price time (UTC) | Delay (min) | Sector / category | 1y obs |
|---|---|---|---|---|---|---|---|---|
| SPY | ETF | State Street SPDR S&P 500 ETF T | 764.2 | USD | 2026-09-29T20:00:00+00:00 | 0 | Large Blend | 251 |
| VOO | ETF | Vanguard S&P 500 ETF | 702.46 | USD | 2026-09-29T20:00:00+00:00 | 0 | Large Blend | 251 |
| QQQ | ETF | Invesco QQQ Trust, Series 1 | 737.93 | USD | 2026-09-29T20:00:00+00:00 | 0 | Large Growth | 251 |
| AAPL | EQUITY | Apple Inc. | 329.4 | USD | 2026-09-29T20:00:00+00:00 | 0 | Technology | 251 |
| NVDA | EQUITY | NVIDIA Corporation | 227.21 | USD | 2026-09-29T20:00:00+00:00 | 0 | Technology | 251 |
| IBIT | ETF | iShares Bitcoin Trust ETF | 47.33 | USD | 2026-09-29T20:00:00+00:00 | 0 | Digital Assets | 251 |
| JPM | EQUITY | JP Morgan Chase & Co. | 334.98 | USD | 2026-09-29T20:00:03+00:00 | 0 | Financial Services | 251 |

## Test portfolio — ETF look-through data

| ETF | Sector weights (n / sum) | Asset classes | Top holdings (n / % of fund) |
|---|---|---|---|
| SPY | 11 / 100.0% | {'cashPosition': 0.0011, 'stockPosition': 0.9988} | 10 / 37.8% |
| VOO | 11 / 100.0% | {'cashPosition': 0.0007, 'stockPosition': 0.9987, 'otherPosition': 0.0006} | 10 / 37.8% |
| QQQ | 11 / 100.0% | {'cashPosition': 0.0011, 'stockPosition': 0.9989} | 10 / 46.3% |
| IBIT | 0 / — | {'otherPosition': 1.0} | 0 / — |

### Top holdings detail

- **SPY**: NVDA 8.1%, AAPL 7.0%, MSFT 5.7%, AMZN 3.8%, GOOGL 3.0%, AVGO 2.6%, GOOG 2.4%, META 1.9%, MU 1.6%, TSLA 1.6%
- **VOO**: NVDA 8.1%, AAPL 7.0%, MSFT 5.7%, AMZN 3.8%, GOOGL 3.0%, AVGO 2.7%, GOOG 2.4%, META 1.9%, MU 1.6%, TSLA 1.6%
- **QQQ**: NVDA 8.5%, AAPL 7.4%, MSFT 6.0%, MU 4.8%, AMZN 4.4%, AMD 3.4%, GOOGL 3.1%, TSLA 2.9%, GOOG 2.9%, AVGO 2.8%

### Sector-weight keys returned (SPY)

`['realestate', 'consumer_cyclical', 'basic_materials', 'consumer_defensive', 'technology', 'communication_services', 'financial_services', 'utilities', 'industrials', 'energy', 'healthcare']`

## Sector proxies (SPDR)

| Ticker | Sector | Price | 1y obs | History range |
|---|---|---|---|---|
| XLK | Technology | 194.5 | 251 | 2025-09-30 → 2026-09-29 |
| XLF | Financials | 54.01 | 251 | 2025-09-30 → 2026-09-29 |
| XLV | Healthcare | 170.73 | 251 | 2025-09-30 → 2026-09-29 |
| XLY | Consumer Discretionary | 109.15 | 251 | 2025-09-30 → 2026-09-29 |
| XLC | Communication Services | 111.47 | 251 | 2025-09-30 → 2026-09-29 |
| XLI | Industrials | 169.13 | 251 | 2025-09-30 → 2026-09-29 |
| XLE | Energy | 61.54 | 251 | 2025-09-30 → 2026-09-29 |
| XLB | Materials | 49.1 | 251 | 2025-09-30 → 2026-09-29 |
| XLP | Consumer Staples | 81.85 | 251 | 2025-09-30 → 2026-09-29 |
| XLU | Utilities | 39.71 | 251 | 2025-09-30 → 2026-09-29 |
| XLRE | Real Estate | 41.34 | 251 | 2025-09-30 → 2026-09-29 |

## Errors

None.

## Findings and recommended decisions

1. **yfinance alone is enough for the MVP.** Every field the brief needs came
   back for all 18 tickers with no errors, and every ticker has 251 aligned
   daily observations. No fallback provider needed.
2. **Only the top 10 holdings are available**, covering 37.8% of SPY/VOO and
   46.3% of QQQ. Look-through at company level will show "other holdings" for
   the remaining 54–62%, as the brief already requires. Sector weights are
   complete (11 sectors, summing to 100%), so sector look-through is full.
3. **Yahoo uses its own sector names**, not GICS labels. Map them:
   `consumer_cyclical`→Consumer Discretionary, `consumer_defensive`→Consumer
   Staples, `basic_materials`→Materials, `financial_services`→Financials,
   `realestate`→Real Estate. Stock sectors use the display form (JPM =
   "Financial Services"), so the map must cover both forms. Yahoo's
   classification is close to GICS but not identical, so the app should say
   "GICS-style sectors (Yahoo classification)".
4. **Fund sector weights describe the equity sleeve only**, and they sum to
   100% even though SPY is 99.88% stock and 0.11% cash. Scale sector weights
   by `stockPosition` so fund cash lands in the cash bucket.
5. **IBIT reports no sectors and 100% `otherPosition`.** Only its category,
   "Digital Assets", identifies it as crypto. Rule: category "Digital Assets"
   → asset class crypto. Otherwise it would fall into "other/unknown".
6. **Alphabet appears twice in the holdings** (GOOGL + GOOG, 5.4% of SPY
   combined). A small share-class alias map (GOOG→GOOGL, BRK-A→BRK-B, …)
   is needed, or Alphabet will look smaller than it is.
7. **Price timing:** prices are the 29 Sep close (20:00 UTC = 4pm ET). Yahoo
   reports `exchangeDataDelayedBy = 0` even so. Don't trust that field.
   Label prices "last price as of <timestamp>" and never "live".
