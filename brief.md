# Portfolio Exposure Visualiser — Brief

## Objective

A Streamlit app that answers: **"What am I actually exposed to?"**

Core idea: **number of tickers ≠ number of independent risk exposures.**
Different tickers can hold the same companies, the same sectors, or move
together historically.

Two uses:

1. **CV piece.** Public, deployed, and good-looking enough to show employers.
2. **Conversation tool.** I type in someone's holdings and walk them through
   their real exposure on screen.

## Stack

- Streamlit + Plotly, deployed like my weekly apps.
- Data: `yfinance` first (prices, sectors, ETF sector weights, ETF top
  holdings). Add a fallback provider only if a real coverage gap appears.
- Free sources usually give only an ETF's **top ~10 holdings**. Show the
  covered % and label the rest as "other holdings". Never rescale to 100%.

## Input

Ticker + number of shares only. US-listed stocks and ETFs, long-only,
fractional shares allowed, USD.

```text
AAPL  10
SPY   20
```

Merge duplicate tickers. If a ticker is invalid or has no price, list it in
a visible warning. Never drop it silently.

## Outputs

- Headline figures: total value, number of positions, largest position,
  largest sector, top-five concentration.
- Allocation by holding and by asset class (equity, fixed income, cash,
  commodities, crypto, other/unknown). "ETF" is a wrapper, not an asset class.
- Sector exposure (GICS 11) with ETFs looked through. Non-equity and
  unclassified amounts stay visible as their own buckets.
- Largest underlying companies, combining direct and indirect ownership, and
  which funds share them.
- Two correlation heatmaps: one for the entered assets, one for sectors.
- A short templated summary: the largest position, the largest sector, the
  most positively correlated asset pair and sector pair, and concentration
  flags. Describe only; never recommend trades.
- Price timestamp, and whether prices are delayed. Do not call delayed data "live".

## Methodology rules (the non-obvious parts)

- Keep **purchased positions** and **underlying exposures** as separate
  views. Never add a fund's value on top of its constituents in one total.
- Use one sector route per fund: the provider's sector weights, or sectors
  derived from its holdings. Never both.
- Unknown exposure ≠ zero exposure. Show data coverage as % of portfolio value.
- Correlations: daily simple returns on adjusted prices, 1-year lookback,
  Pearson, aligned dates, no forward-filling. Show the window and number of
  observations beside each heatmap. If history is too short, say so.
- Asset correlations use each security's own return history. Never rebuild
  ETF history from today's holdings.
- Sector correlations use the SPDR sector ETFs (XLK, XLF, …) as proxies, and
  only for sectors with positive exposure.
- "Most correlated" means the highest positive correlation among distinct
  pairs. If no pair is positive, say so.

## Data decisions (from Step 1, `scratch/coverage_report.md`)

1. yfinance is the only provider for v1. Company look-through uses each
   ETF's **top 10 holdings**. The rest shows as "other holdings", never
   rescaled. Sector look-through uses the fund's full sector weights.
2. Map Yahoo sector names (both `consumer_cyclical` and "Consumer
   Cyclical" forms) to the 11 GICS labels. Label the chart "GICS-style
   sectors (Yahoo classification)".
3. Multiply fund sector weights by the fund's `stockPosition`. Fund cash
   goes to the cash bucket.
4. A fund whose category is "Digital Assets" counts as crypto.
5. Merge share classes with an alias map (GOOG→GOOGL, BRK-A→BRK-B, …).
6. Ignore Yahoo's delay flag. Label prices "last price as of \<timestamp\>".

## Look & feel

Sophisticated, approachable, and visually engaging. Exploring a portfolio
should feel intuitive.

- **Reference screenshots are in `refs/`**:
  - `refs/dominion-home.png`: typography, spacing, dark backdrop, violet accents.
  - `refs/dominion-factsheet-charts.png`: colourful pies and horizontal bars.
    This is the chart reference.
- **Theme:** dark navy or charcoal header, with white or very pale lavender
  chart panels. Electric violet for primary buttons and selected states.
- **Colour:** the charts carry the energy (violet, green, yellow, amber,
  peach, coral, pink). Keep the interface around them simple. Each sector
  keeps the same colour throughout the app.
- **Typography:** Montserrat or a similar rounded geometric font. Large
  headings, prominent headline numbers, readable labels.
- **Charts:** large donuts for allocation; ranked horizontal bars for sectors
  and holdings; clear heatmaps. Show percentages, use subtle gridlines, add
  helpful hover details.
- **Page flow:** input → headline figures → allocation & sector exposure →
  underlying holdings & overlap → correlation heatmaps → summary.
- **Interaction:** one scrolling page I can talk someone through. Main insights
  show immediately; detailed tables and explanations sit in expanders.
- **Avoid:** the generic Streamlit look, crowded navigation, cluttered
  sidebars, tiny charts, lots of tables, long text blocks.

Target reaction: *"This looks compelling, I immediately know where to start,
and the charts help me understand my investments."*

## Test portfolio

```text
SPY   20
VOO   10
QQQ   15
AAPL  10
NVDA   5
IBIT  20
JPM    8
```

Expected story: seven tickers, but SPY/VOO are near-identical, and
QQQ/SPY/VOO all hold AAPL and NVDA on top of the direct positions. IBIT adds
a separate crypto exposure.

## Acceptance checks

- Weights sum to 100%. Sector buckets plus non-equity plus unknown sum to 100%.
- An ETF at 20% of the portfolio with 40% Technology adds 8pp to Technology.
- AAPL's total = direct weight + the look-through from each fund. No value
  is double-counted.
- Charts, tables, and summary show the same numbers.
- Invalid tickers, short histories, and provider failures produce clear
  messages, not crashes.

## Out of scope (v1)

Optimisation, forecasts, trade recommendations, buy/sell signals, user
accounts, brokerage connections, saved portfolios, nested fund-of-funds,
and leveraged/inverse fund modelling (flag these as unsupported).

## Before building

Give me a step plan first. Check that `yfinance` returns sector weights and
top holdings for every ETF in the test portfolio before any UI work.
