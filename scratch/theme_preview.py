"""Step 7 preview: one of each component on the test portfolio.

Run from the project folder:
    ../../.venv/bin/streamlit run scratch/theme_preview.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402

from portfolio import charts, theme  # noqa: E402
from portfolio.correlation import asset_correlation, sector_correlation  # noqa: E402
from portfolio.data import FixtureSource, load_market_data, parse_holdings  # noqa: E402
from portfolio.exposure import compute_exposure  # noqa: E402

st.set_page_config(page_title="Theme preview", page_icon="◐", layout="wide")
st.markdown(theme.CSS, unsafe_allow_html=True)

holdings, _ = parse_holdings("SPY 20\nVOO 10\nQQQ 15\nAAPL 10\nNVDA 5\nIBIT 20\nJPM 8")
md = load_market_data(holdings, FixtureSource())
ex = compute_exposure(md)
c = ex.concentration

st.markdown(
    """
<div class="hmp-hero">
  <div class="hmp-pill">◐ Theme preview · Step 7</div>
  <h1>What are you actually<br>exposed to?</h1>
  <p>Seven tickers can hide far fewer independent bets. Look through the funds to see
  the companies, sectors, and co-movement underneath.</p>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown(
    f"""
<div class="hmp-cards">
  <div class="hmp-card"><div class="label">Portfolio value</div><div class="value">${ex.total_value:,.0f}</div>
    <div class="note">last price 29 Sep 2026 close</div></div>
  <div class="hmp-card accent"><div class="label">Tickers → effective positions</div>
    <div class="value">{c['n_positions']} → {c['effective_positions']:.1f}</div><div class="note">by weight</div></div>
  <div class="hmp-card"><div class="label">Largest sector</div><div class="value">{c['largest_sector_weight']:.1%}</div>
    <div class="note">{c['largest_sector']}</div></div>
  <div class="hmp-card"><div class="label">Largest company</div><div class="value">{c['largest_company_weight']:.1%}</div>
    <div class="note">{c['largest_company']}, direct + through funds</div></div>
</div>
""",
    unsafe_allow_html=True,
)

st.button("Analyse portfolio")

st.markdown('<div class="hmp-h2">Palette</div><div class="hmp-sub">Top: factsheet pixels. '
            'Bottom: same hues fitted for the dark panels (used by the app).</div>', unsafe_allow_html=True)
with st.container(key="panel-palette"):
    for name, pal in (("Reference", theme.REFERENCE), ("App (fitted for dark panels)", theme.COLORS)):
        sw = "".join(f'<div class="hmp-swatch"><div style="background:{h}"></div>{k}<br>{h}</div>'
                     for k, h in pal.items())
        st.markdown(f"**{name}**<div class='hmp-swatches'>{sw}</div>", unsafe_allow_html=True)

st.markdown('<div class="hmp-h2">Allocation and sector exposure</div>', unsafe_allow_html=True)
left, right = st.columns([5, 6], gap="medium")
with left, st.container(key="panel-donut"):
    st.markdown("### Asset classes")
    st.markdown('<p class="hmp-caption">Funds looked through · share of portfolio value</p>', unsafe_allow_html=True)
    st.plotly_chart(charts.donut(ex.asset_classes, ex.total_value), width="stretch", theme=None)
with right, st.container(key="panel-sectors-a"):
    st.markdown("### Sectors — option A: one colour per sector")
    sec = ex.sectors.query("kind == 'sector' and weight > 0")
    st.plotly_chart(
        charts.ranked_bars(list(sec["bucket"]), list(sec["weight"]),
                           [theme.SECTOR_COLORS[s] for s in sec["bucket"]]),
        width="stretch", theme=None,
    )

left, right = st.columns([5, 6], gap="medium")
with left, st.container(key="panel-positions"):
    st.markdown("### Positions as bought")
    st.plotly_chart(
        charts.ranked_bars(list(ex.positions["ticker"]), list(ex.positions["weight"]), theme.COLORS["violet"]),
        width="stretch", theme=None,
    )
with right, st.container(key="panel-sectors-b"):
    st.markdown("### Sectors — option B: single violet")
    st.plotly_chart(charts.ranked_bars(list(sec["bucket"]), list(sec["weight"]), theme.COLORS["violet"]),
                    width="stretch", theme=None)

st.markdown('<div class="hmp-h2">Underlying companies</div>', unsafe_allow_html=True)
with st.container(key="panel-companies"):
    st.markdown("### Top 10 companies, direct + through funds")
    st.plotly_chart(charts.company_bars(ex.companies), width="stretch", theme=None)
    with st.expander("Show table"):
        st.dataframe(ex.companies.head(10), hide_index=True)

st.markdown('<div class="hmp-h2">Correlation</div>', unsafe_allow_html=True)
a, s = asset_correlation(md, ex), sector_correlation(md, ex)
left, right = st.columns([5, 7], gap="medium")
with left, st.container(key="panel-heat-assets"):
    st.markdown("### Holdings")
    st.markdown(f'<p class="hmp-caption">{a.window_label}</p>', unsafe_allow_html=True)
    st.plotly_chart(charts.heatmap(a), width="stretch", theme=None)
with right, st.container(key="panel-heat-sectors"):
    st.markdown("### Sectors (SPDR proxies)")
    st.markdown(f'<p class="hmp-caption">{s.window_label}</p>', unsafe_allow_html=True)
    st.plotly_chart(charts.heatmap(s), width="stretch", theme=None)
