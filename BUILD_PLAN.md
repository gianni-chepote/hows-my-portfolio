# Build Plan — How's My Portfolio?

Source of truth: `brief.md`. Build the required minimum first: working,
tested, deployed. Extensions come only in Phase 5.

Each step lists its goal, what it produces, a proxy prompt to paste, and a
"done when" check. Do one step per session and `/clear` between steps.

## Target layout

```text
hows-my-portfolio/
├── brief.md, BUILD_PLAN.md, refs/
├── streamlit_app.py          ← entrypoint at root (Streamlit Cloud)
├── requirements.txt          ← app-only: streamlit, plotly, pandas, numpy, yfinance
├── .streamlit/config.toml    ← theme
├── portfolio/                ← pure logic, no Streamlit imports
│   ├── data.py               ← yfinance fetch + normalise + cache
│   ├── exposure.py           ← weights, asset classes, sectors, look-through
│   ├── correlation.py        ← returns + both heatmap matrices
│   ├── summary.py            ← templated text
│   └── theme.py              ← palette, sector colours, Plotly template, CSS
├── fixtures/                 ← saved snapshot of the test portfolio's data
├── tests/
└── scratch/                  ← spikes, never imported by the app
```

Keeping `portfolio/` free of Streamlit means every number can be tested
offline against fixtures.

---

## Phase 1 — Data feasibility

### Step 1: yfinance coverage check

- **Goal:** find out what yfinance actually returns for the test portfolio
  before designing anything else around it.
- **Produces:**
  - `scratch/01_coverage.py`
  - `scratch/coverage_report.md`: for each ticker, whether we get a price,
    the quote type, sector, fund sector weights, top holdings (count + % of
    fund covered), asset-class split, 1-year history length, and any errors.
- **Proxy prompt:**
  > Read `hows-my-portfolio/brief.md`. Do Step 1 of `BUILD_PLAN.md`: write
  > `scratch/01_coverage.py`, which pulls every field the brief needs for the
  > test portfolio (SPY, VOO, QQQ, AAPL, NVDA, IBIT, JPM) and the 11 SPDR
  > sector ETFs through yfinance. Save the findings table to
  > `scratch/coverage_report.md`. Flag any gaps, and flag how IBIT
  > (crypto) is classified. No app code yet.
- **Done when:** the report shows, for each ticker, what is available and
  what isn't. You decide whether yfinance alone is enough. **This is a
  decision gate: stop here and review.**

### Step 2: Fixtures

- **Goal:** freeze one real data snapshot so tests don't depend on the network.
- **Produces:**
  - `fixtures/`: prices, histories, and fund data for the test portfolio,
    saved as parquet/json
  - `fixtures/README.md` with the date they were pulled
- **Proxy prompt:**
  > Do Step 2 of `BUILD_PLAN.md`: save a fixture snapshot of every yfinance
  > field Step 1 confirmed, for the test portfolio and the sector ETFs.
- **Done when:** the fixtures load offline and the date they were pulled
  is recorded.

---

## Phase 2 — Calculation engine (no UI)

### Step 3: Data layer

- **Goal:** one clean interface between yfinance and the rest of the app.
- **Produces:**
  - `portfolio/data.py`: parse the ticker/shares input (merge duplicates,
    validate symbols), fetch everything, and normalise it into tidy
    dataframes with explicit "missing" flags
  - an option to load from fixtures instead of the network
- **Proxy prompt:**
  > Do Step 3 of `BUILD_PLAN.md`. Build `portfolio/data.py` following the
  > brief's Input section. It should be able to load from fixtures. Add tests
  > for input parsing (duplicates, fractional shares, bad tickers, blank
  > lines).
- **Done when:** the parser tests pass and the test portfolio loads from
  fixtures with no network calls.

### Step 4: Exposure engine

- **Goal:** all the numbers except correlations.
- **Produces:** `portfolio/exposure.py`, covering:
  - position values and weights
  - asset-class split
  - GICS sector exposure with look-through, plus non-equity and unknown buckets
  - largest underlying companies (direct + indirect) and which funds share them
  - coverage %
  - top-five concentration
- **Proxy prompt:**
  > Do Step 4 of `BUILD_PLAN.md`. Build `portfolio/exposure.py` following
  > the brief's Methodology rules. Write tests for every Acceptance check
  > that doesn't involve correlation, using the fixtures and a small
  > hand-made portfolio.
- **Done when:**
  - all of these acceptance tests pass: weights sum to 100%, sector buckets
    sum to 100%, the 20%×40% example gives 8pp, and AAPL's direct and
    indirect ownership combine without double counting
  - on the test portfolio, AAPL and NVDA show more total exposure than
    their direct positions

### Step 5: Correlation engine

- **Goal:** both heatmap matrices and the "most correlated pair" logic.
- **Produces:** `portfolio/correlation.py`, covering:
  - aligned daily simple returns over a 1-year lookback
  - the asset matrix
  - the sector-proxy matrix (only sectors with exposure)
  - the top distinct positive pair
  - the observation-window metadata
- **Proxy prompt:**
  > Do Step 5 of `BUILD_PLAN.md`. Build `portfolio/correlation.py` following
  > the brief's correlation rules. Test it with short histories, a constant
  > series, the case where no pair is positive, and the test portfolio.
- **Done when:**
  - the tests pass
  - SPY/VOO come out as the top pair on the test portfolio (expected ≈ 1.0)

### Step 6: Summary text

- **Goal:** a short templated summary built only from the engine's outputs.
- **Produces:** `portfolio/summary.py`.
- **Proxy prompt:**
  > Do Step 6 of `BUILD_PLAN.md`. Build the templated summary from the
  > brief's Outputs section. It must read its numbers from the engine
  > outputs, disclose coverage gaps, and use no advice language. Test that
  > every number in the text matches the engine.
- **Done when:** the summary for the test portfolio reads well and every
  number in it traces back to the engine.

---

## Phase 3 — Look & dashboard

### Step 7: Theme and chart kit

- **Goal:** the Dominion look, built once and reused everywhere.
- **Produces:**
  - `.streamlit/config.toml`
  - `portfolio/theme.py`:
    - the palette taken from `refs/dominion-factsheet-charts.png`
      (violet, green, yellow, amber, peach, coral, pink, then lavender,
      navy, and teal)
    - a fixed sector→colour map
    - a Plotly template with Montserrat, subtle gridlines, and % labels
    - CSS for a dark header, pale panels, violet buttons, and headline
      number cards
  - `scratch/theme_preview.py`: one of each chart type on dummy data
- **Proxy prompt:**
  > Do Step 7 of `BUILD_PLAN.md`. Look at both images in `refs/` and the
  > brief's Look & feel section. Build the theme, the Plotly template, the
  > sector colour map, and the CSS. Make a `scratch/theme_preview.py` page
  > showing a donut, a ranked horizontal bar, a heatmap, and the headline
  > cards, then screenshot it so I can compare it with the refs.
- **Done when:** you compare the preview with the refs and approve it.
  **This is a decision gate.**

### Step 8: Dashboard assembly

- **Goal:** the full single-page app, following the brief's page flow.
- **Produces:** `streamlit_app.py`, laid out as:
  1. input box
  2. headline cards
  3. allocation donut + sector bars
  4. underlying holdings & overlap (tables in expanders)
  5. both heatmaps
  6. summary

  Results are cached, and the test portfolio is pre-filled as the demo.
- **Proxy prompt:**
  > Do Step 8 of `BUILD_PLAN.md`. Assemble `streamlit_app.py` in the
  > brief's page-flow order, using only `portfolio/` functions and the Step 7
  > theme. Pre-fill the test portfolio. Run it and screenshot the full page.
- **Done when:** the app runs locally, the page looks like the refs, and
  the charts, tables, and summary all show the same numbers.

---

## Phase 4 — Harden & ship

### Step 9: Failure handling and smoke tests

- **Goal:** no crashes in front of an employer or a client.
- **Produces:**
  - visible warnings for invalid tickers, missing prices, short histories,
    a yfinance outage, and leveraged or inverse funds
  - `tests/test_app_smoke.py` using Streamlit's AppTest
- **Proxy prompt:**
  > Do Step 9 of `BUILD_PLAN.md`. Walk through every failure case in the
  > brief and make each one show a clear message. Add AppTest smoke tests for
  > the demo portfolio and for a portfolio with bad input.
- **Done when:** the full test suite passes and none of the listed cases
  crashes.

### Step 10: Deploy

- **Goal:** a public URL you can put on your CV.
- **Produces:**
  - a nested git repo in this folder (same approach as Revelatio)
  - a public GitHub repo, created with `gh repo create`
  - a Streamlit Cloud app with a custom subdomain
  - a `README.md` with a screenshot and a methodology note
- **Proxy prompt:**
  > Do Step 10 of `BUILD_PLAN.md`. Write the README, `git init` in place,
  > create a public repo with gh, and push. Then tell me the Streamlit Cloud
  > steps I do in the browser.
- **Done when:** the live URL loads without a login and the demo portfolio
  renders.

---

## Phase 5 — Extensions (only after Phase 4 ships)

Pick any of these, in any order:

- **Effective number of bets:** turn "7 tickers ≈ N real exposures" into a
  headline number, derived from the correlation matrix's eigenvalues.
- **Fund overlap matrix:** a heatmap of the % of holdings each pair of
  funds shares.
- **Geography exposure:** add the factsheet's "Top Geographies" bar.
- **Shareable link:** encode the portfolio in URL query params so a client
  can reopen their view later.
- **PDF snapshot:** a one-page factsheet-style export to hand a client.
- **CSV / IBKR import:** paste or upload holdings instead of typing them.
