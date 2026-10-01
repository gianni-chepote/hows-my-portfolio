"""How's My Portfolio? — what are you actually exposed to?

One scrolling page, in the brief's order:
input → headline figures → allocation & sectors → underlying companies →
correlation → summary.

All numbers come from the `portfolio` package; this file only lays them out.
Set HMP_DATA=fixtures to run on the frozen snapshot instead of live Yahoo data.
"""

from __future__ import annotations

import html
import itertools
import os
from zoneinfo import ZoneInfo

import streamlit as st

from portfolio import charts, theme
from portfolio.correlation import asset_correlation, ranked_pairs, sector_correlation
from portfolio.data import FixtureSource, YahooSource, load_market_data, parse_holdings
from portfolio.exposure import OTHER_HOLDINGS, compute_exposure
from portfolio.summary import build_summary

DEMO_PORTFOLIO = "SPY   20\nVOO   10\nQQQ   15\nAAPL  10\nNVDA   5\nIBIT  20\nJPM    8"
CHART_CONFIG = {"displayModeBar": False, "responsive": True}

st.set_page_config(page_title="How's My Portfolio?", page_icon="◐", layout="wide")
st.markdown(theme.CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------- data


def _source():
    return FixtureSource() if os.environ.get("HMP_DATA") == "fixtures" else YahooSource()


@st.cache_data(ttl=900, show_spinner=False)
def analyse(text: str) -> dict:
    """Parse, fetch, and compute everything for one input. Cached for 15 minutes."""
    holdings, issues = parse_holdings(text)
    if holdings.empty:
        return {"issues": issues}
    md = load_market_data(holdings, _source())
    issues = issues + md.issues
    if md.quotes.empty:
        return {"issues": issues}
    ex = compute_exposure(md)
    assets, sectors = asset_correlation(md, ex), sector_correlation(md, ex)
    return {
        "issues": issues,
        "md": md,
        "ex": ex,
        "assets": assets,
        "sectors": sectors,
        "summary": build_summary(ex, assets, sectors, issues),
    }


_chart_ids = itertools.count()


def plot(build) -> None:
    """Draw the chart once per colour mode; CSS shows the one matching the system setting."""
    n = next(_chart_ids)
    for mode in theme.MODES:
        with st.container(key=f"chart-{mode}-{n}"):
            st.plotly_chart(build(mode), width="stretch", theme=None, config=CHART_CONFIG, key=f"fig-{mode}-{n}")


def heading(title: str, sub: str = "") -> None:
    st.markdown(f'<div class="hmp-h2">{title}</div>' + (f'<div class="hmp-sub">{sub}</div>' if sub else ""),
                unsafe_allow_html=True)


def caption(text: str) -> None:
    st.markdown(f'<p class="hmp-caption">{text}</p>', unsafe_allow_html=True)


def pct(x: float) -> str:
    return f"{x:.1%}"


def no_latex(text: str) -> str:
    """Markdown treats paired $ signs as maths; use the HTML entity instead."""
    return text.replace("$", "&#36;")


# --------------------------------------------------------------------------- hero & input

st.markdown(
    """
<div class="hmp-hero">
  <div class="hmp-pill">◐ Portfolio exposure</div>
  <h1>What are you actually<br>exposed to?</h1>
  <p>Different tickers can hold the same companies, the same sectors, or move together.
  Enter your holdings to see the exposure underneath.</p>
  <div class="hmp-byline">By <b>Gianni Chepote</b> · <a href="https://github.com/gianni-chepote" target="_blank">GitHub</a>
  · <a href="https://github.com/gianni-chepote/hows-my-portfolio" target="_blank">Source code</a></div>
</div>
""",
    unsafe_allow_html=True,
)

if "portfolio_text" not in st.session_state:
    st.session_state.portfolio_text = DEMO_PORTFOLIO

with st.container(key="panel-input"):
    left, right = st.columns([3, 2], gap="large")
    with left, st.form("portfolio", border=False):
        text = st.text_area(
            "Holdings: one per line, ticker then number of shares",
            value=st.session_state.portfolio_text,
            height=210,
        )
        submitted = st.form_submit_button("Analyse portfolio")
    with right:
        st.markdown(
            """
<div class="hmp-help">
<b>How to enter holdings</b><br>
One line per position: <code>AAPL 10</code>. Fractional shares work (<code>VOO 2.5</code>),
and repeated tickers are added together.<br><br>
US-listed stocks and ETFs, long positions, priced in USD. The demo portfolio is pre-filled:
replace it with your own.<br><br>
Prices are the last available from Yahoo Finance, not live quotes.
</div>
""",
            unsafe_allow_html=True,
        )
if submitted:
    st.session_state.portfolio_text = text

try:
    with st.spinner("Fetching prices and fund holdings…"):
        result = analyse(st.session_state.portfolio_text)
except Exception:  # noqa: BLE001 - last line of defence: never show a traceback
    st.error("Something went wrong while loading market data. Please try again in a few minutes; "
             "if it keeps happening, check the tickers you entered.")
    st.stop()

for issue in result["issues"]:
    {"error": st.error, "warning": st.warning, "info": st.info}[issue.level](issue.message)

if "ex" not in result:
    st.stop()

md, ex, assets, sectors, summary = (result[k] for k in ("md", "ex", "assets", "sectors", "summary"))
c = ex.concentration

# --------------------------------------------------------------------------- headline figures

as_of = md.as_of
as_of_text = as_of.astimezone(ZoneInfo("America/New_York")).strftime("%d %b %Y, %-I:%M %p ET") if as_of else "unknown"
positions_word = "position" if c["n_positions"] == 1 else "positions"

st.markdown(
    f"""
<div class="hmp-cards" style="margin-top:1.75rem">
  <div class="hmp-card">
    <div class="label">Portfolio value</div>
    <div class="value">&#36;{ex.total_value:,.0f}</div>
    <div class="note">USD · last price {as_of_text}</div>
  </div>
  <div class="hmp-card accent" title="1 ÷ the sum of squared position weights. Equal weights give the ticker count; one dominant position pulls it towards 1.">
    <div class="label">Tickers → effective positions ⓘ</div>
    <div class="value">{c['n_positions']} → {c['effective_positions']:.1f}</div>
    <div class="note">{c['n_positions']} {positions_word}, weighted like {c['effective_positions']:.1f} equal ones</div>
  </div>
  <div class="hmp-card" title="Direct stocks plus each fund's sector weights, scaled by the fund's size in the portfolio.">
    <div class="label">Largest sector ⓘ</div>
    <div class="value">{pct(c['largest_sector_weight']) if c['largest_sector'] else '—'}</div>
    <div class="note">{c['largest_sector'] or 'No sector data'}, funds looked through</div>
  </div>
  <div class="hmp-card" title="Direct shares plus the company's weight inside each fund you own (top 10 fund holdings only).">
    <div class="label">Largest company ⓘ</div>
    <div class="value">{pct(c['largest_company_weight']) if c['largest_company'] else '—'}</div>
    <div class="note">{c['largest_company'] or 'No company data'}, direct + through funds</div>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- allocation & sectors

heading("Allocation and sector exposure", "What you bought, and what it adds up to once funds are looked through.")

left, right = st.columns([6, 5], gap="medium")
with left, st.container(key="panel-positions"):
    st.markdown("### Positions as bought")
    caption("Share of portfolio value by ticker")
    pos = ex.positions
    plot(lambda mode: charts.ranked_bars(
        list(pos["ticker"]), list(pos["weight"]), theme.VIOLET,
        hover_extra=[f"<br>{html.escape(str(n))}<br>{w} · ${v:,.0f}"
                     for n, w, v in zip(pos["name"], pos["wrapper"], pos["value"])],
        mode=mode,
    ))
    with st.expander("Show positions table"):
        table = pos[["ticker", "name", "wrapper", "shares", "price", "value", "weight"]].rename(columns={
            "ticker": "Ticker", "name": "Name", "wrapper": "Type", "shares": "Shares",
            "price": "Last price ($)", "value": "Value ($)", "weight": "Weight",
        })
        st.dataframe(
            table, hide_index=True, width="stretch",
            column_config={
                "Last price ($)": st.column_config.NumberColumn(format="dollar"),
                "Value ($)": st.column_config.NumberColumn(format="dollar"),
                "Weight": st.column_config.NumberColumn(format="percent"),
                "Shares": st.column_config.NumberColumn(format="%g"),
            },
        )
with right, st.container(key="panel-assets"):
    st.markdown("### Asset classes")
    caption("Funds looked through · ETF is a wrapper, not an asset class")
    plot(lambda mode: charts.donut(ex.asset_classes, ex.total_value, mode=mode))

with st.container(key="panel-sectors"):
    st.markdown("### Sector exposure")
    caption("GICS-style sectors (Yahoo classification) · direct stocks plus each fund's sector weights")
    sec = ex.sectors[ex.sectors["weight"] > 0.0005]
    in_sector = sec[sec["kind"] == "sector"].sort_values("weight", ascending=False)
    outside = sec[sec["kind"] != "sector"].sort_values("weight", ascending=False)  # grouped below the sectors
    buckets = list(in_sector["bucket"]) + list(outside["bucket"])
    weights = list(in_sector["weight"]) + list(outside["weight"])
    plot(lambda mode: charts.ranked_bars(
        buckets, weights, [theme.MODES[mode].color(b) for b in buckets], sort=False, mode=mode,
    ))
    if ex.coverage["sector_known"] < 0.995:
        st.markdown(
            f'<div class="hmp-callout"><b>{pct(1 - ex.coverage["sector_known"])}</b> of the portfolio has no sector '
            "data and is shown as unknown or unclassified, not as zero.</div>",
            unsafe_allow_html=True,
        )

# --------------------------------------------------------------------------- underlying companies

heading("Underlying companies", "The same company can reach you directly and through several funds.")

with st.container(key="panel-companies"):
    co = ex.companies
    if co.empty:
        st.markdown("### Top companies")
        caption("No company-level data for these holdings.")
    else:
        st.markdown(f"### Top {min(10, len(co))} companies, direct + through funds")
        caption("Hover a bar to see which funds hold it")
        shared = int((co.head(10)["n_sources"] >= 2).sum())
        named = ex.coverage["equity_named"]
        undisclosed = ex.coverage["equity_undisclosed"]
        callout = f"<b>{shared} of the top {min(10, len(co))}</b> companies reach you through two or more positions."
        if named is not None and undisclosed > 0.005:
            callout += (f" Company figures cover <b>{pct(named)}</b> of your equity exposure; the other "
                        f"<b>{pct(undisclosed)}</b> of the portfolio sits in {OTHER_HOLDINGS.lower()}, because the data "
                        "source lists only each fund's top 10.")
        st.markdown(f'<div class="hmp-callout">{callout}</div>', unsafe_allow_html=True)
        plot(lambda mode: charts.company_bars(co, mode=mode))
        with st.expander("Show company table"):
            via_cols = [col for col in co.columns if col.startswith("via ")]
            cols = ["symbol", "name"] + (["direct"] if "direct" in co else []) + via_cols + ["total", "n_sources"]
            pct_cols = [col for col in cols if col in via_cols + ["direct", "total"]]
            st.dataframe(
                co[cols].rename(columns={"symbol": "Symbol", "name": "Name", "direct": "Direct", "total": "Total",
                                         "n_sources": "Held via"}),
                hide_index=True, width="stretch",
                column_config={
                    ("Direct" if col == "direct" else "Total" if col == "total" else col):
                        st.column_config.NumberColumn(format="percent")
                    for col in pct_cols
                },
            )

# --------------------------------------------------------------------------- correlation

heading(
    "How your holdings move together",
    "Correlation of daily returns over the past year: 1 means they move as one, 0 means unrelated. "
    "It describes the past, not a forecast.",
)

left, right = st.columns([7, 4], gap="medium")
with left, st.container(key="panel-heat-assets"):
    st.markdown("### Holdings")
    caption(f"{assets.window_label} · each pair shown once")
    if assets.ok:
        plot(lambda mode: charts.heatmap(assets, mode=mode))
    else:
        st.markdown('<div class="hmp-callout">Correlations need at least two holdings with enough price '
                    "history.</div>", unsafe_allow_html=True)
with right, st.container(key="panel-pairs"):
    st.markdown("### Most correlated pairs")
    caption("Highest first · distinct holdings only")
    pairs = ranked_pairs(assets)[:5]
    if pairs:
        items = "".join(f"<li><span>{a} · {b}</span><b>{r:.2f}</b></li>" for a, b, r in pairs)
        st.markdown(f'<ul class="hmp-pairs">{items}</ul>', unsafe_allow_html=True)
        if pairs[0][2] >= 0.95:
            st.markdown(
                f'<div class="hmp-callout" style="margin-top:1rem"><b>{pairs[0][0]}</b> and <b>{pairs[0][1]}</b> '
                "moved almost identically.</div>",
                unsafe_allow_html=True,
            )
    else:
        caption("Not enough price history.")
    if assets.excluded:
        caption("Left out: " + "; ".join(f"{k} ({v})" for k, v in assets.excluded.items()))

with st.container(key="panel-heat-sectors"):
    st.markdown("### Sectors you hold")
    caption(f"{sectors.window_label} · SPDR sector ETFs as proxies (XLK, XLF, …), only sectors with exposure. "
            "US sector funds can differ from the global holdings of some ETFs.")
    if sectors.ok:
        plot(lambda mode: charts.heatmap(sectors, mode=mode))
    else:
        st.markdown('<div class="hmp-callout">Sector correlations need exposure to at least two sectors '
                    "with enough price history.</div>", unsafe_allow_html=True)
    if sectors.excluded:
        caption("Left out: " + "; ".join(f"{k} ({v})" for k, v in sectors.excluded.items()))

# --------------------------------------------------------------------------- summary

heading("Summary")
with st.container(key="panel-summary"):
    bullets = "".join(f"<li>{html.escape(p.text)}</li>" for p in summary.points)
    st.markdown(
        no_latex(f'<div class="hmp-summary"><p class="hmp-summary-head">{html.escape(summary.headline)}</p>'
                 f"<ul>{bullets}</ul></div>"),
        unsafe_allow_html=True,
    )

st.markdown(
    """
<div class="hmp-footer">
Data: Yahoo Finance via yfinance. Prices are the last available, not live. Fund look-through uses each
fund's reported sector weights and top 10 holdings.<br>
Descriptive only: this page does not recommend buying or selling anything.<br>
Built by <a href="https://github.com/gianni-chepote" target="_blank">Gianni Chepote</a>.
</div>
""",
    unsafe_allow_html=True,
)
