"""Dominion-inspired look: palette, fixed colour maps, Plotly templates, CSS.

The page follows the viewer's system setting: light or dark. Each mode has its
own surfaces, ink, and chart colours; the CSS switches on
`prefers-color-scheme`, and the app draws every chart once per mode and shows
only the one that matches (see `plot` in streamlit_app.py).

Dark hues come from refs/dominion-factsheet-charts.png, fitted in OKLCH for the
dark panel (scratch/07b_dark_palette.py). Light hues are the same hues, a step
deeper so thin bars still read on white.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import plotly.graph_objects as go
import plotly.io as pio

from portfolio.exposure import (
    CASH, COMMODITIES, CRYPTO, EQUITY, FIXED_INCOME, OTHER, UNCLASSIFIED_EQUITY, UNKNOWN,
)

FONT = "Montserrat, 'Helvetica Neue', Arial, sans-serif"
VIOLET = "#5A54FF"        # primary accent: buttons, selected states (same in both modes)
VIOLET_HOVER = "#6F6AFF"

# --------------------------------------------------------------------------- palette

REFERENCE = {  # factsheet pixels, for the preview only
    "violet": "#5A54FF", "green": "#8ED976", "yellow": "#FFF67A", "amber": "#FED072",
    "peach": "#F39D73", "coral": "#EE7170", "pink": "#EB77AA", "lavender": "#9C8BC2",
    "navy": "#2A496B", "teal": "#408175",
}

_DARK_COLORS = {
    "violet": "#5A54FF", "green": "#7FC765", "yellow": "#E6DD5A", "amber": "#EFC05B",
    "peach": "#EF986D", "coral": "#ED7473", "pink": "#E876A8", "lavender": "#A08BCE",
    "navy": "#4F82C8", "teal": "#3CA694", "sky": "#5EADE2",
    # Non-sector buckets: hues the sectors don't use.
    "magenta": "#D06BDB", "cyan": "#4CCFD8", "gold": "#C9A15A", "slate": "#8FA3BF",
    "olive": "#A9B85A", "dusk": "#8582B8",
}
_LIGHT_COLORS = {
    "violet": "#5A54FF", "green": "#5BAF45", "yellow": "#D2BE2C", "amber": "#E5A630",
    "peach": "#E8845A", "coral": "#E05A59", "pink": "#DA5C95", "lavender": "#8B74C2",
    "navy": "#2F62A8", "teal": "#2A8E7D", "sky": "#3A93CF",
    "magenta": "#B23DBD", "cyan": "#1DA5B0", "gold": "#A87C2E", "slate": "#6C7F99",
    "olive": "#7F8C2E", "dusk": "#6E6AA6",
}

# Sector -> colour name, same order as the factsheet's equity-sector chart.
# Colour follows the sector, never its rank.
_SECTOR_HUES = {
    "Technology": "violet",
    "Financials": "green",
    "Healthcare": "yellow",
    "Consumer Discretionary": "amber",
    "Industrials": "peach",
    "Communication Services": "coral",
    "Consumer Staples": "pink",
    "Materials": "lavender",
    "Energy": "navy",
    "Utilities": "teal",
    "Real Estate": "sky",
}
# Everything that isn't a sector. Same hue in the sector bars and the donut.
_BUCKET_HUES = {
    EQUITY: "violet",
    FIXED_INCOME: "cyan",
    CRYPTO: "magenta",
    COMMODITIES: "gold",
    CASH: "slate",
    OTHER: "olive",
    UNCLASSIFIED_EQUITY: "dusk",
}

# Asset classes in donut order.
ASSET_ORDER = [EQUITY, FIXED_INCOME, CRYPTO, COMMODITIES, CASH, OTHER, UNKNOWN]


@dataclass(frozen=True)
class Mode:
    name: str
    shell: str            # page background
    panel: str            # cards and chart panels
    panel_line: str       # card border
    ink: str              # primary text
    ink_2: str            # secondary text, value labels
    muted: str            # axis ticks, captions
    grid: str             # gridlines: visible but recessive
    hover_bg: str
    neutral: str          # Unknown: no data, so no hue
    heat_text: str        # heatmap cell labels
    corr_scale: list
    colors: dict = field(default_factory=dict)

    @property
    def template(self) -> str:
        return f"hmp-{self.name}"

    def color(self, bucket: str) -> str:
        """Colour for a sector, asset class, or other bucket; grey only for Unknown."""
        hue = _SECTOR_HUES.get(bucket) or _BUCKET_HUES.get(bucket)
        return self.colors[hue] if hue else self.neutral


DARK = Mode(
    name="dark",
    shell="#07061A", panel="#12112B", panel_line="#2A2D5C",
    ink="#F4F3FF", ink_2="#C4C3DE", muted="#8C8BAE", grid="#24234A", hover_bg="#262454",
    neutral="#6E6D8C", heat_text="#F4F3FF",
    # Diverging around a dark grey at 0: coral below, brand violet above.
    corr_scale=[[0.0, "#C9504F"], [0.25, "#8A3D3E"], [0.5, "#2D2D38"],
                [0.70, "#423B85"], [0.85, "#5847CF"], [1.0, "#6F5AF0"]],
    colors=_DARK_COLORS,
)
LIGHT = Mode(
    name="light",
    shell="#F5F4FB", panel="#FFFFFF", panel_line="#E2E0F0",
    ink="#16152E", ink_2="#4A4868", muted="#76749A", grid="#ECEAF5", hover_bg="#FFFFFF",
    neutral="#A9A8BC", heat_text="#16152E",
    # Diverging around a pale grey at 0; both ends stay light enough for dark labels.
    corr_scale=[[0.0, "#E58180"], [0.25, "#F3C3C2"], [0.5, "#F1F0F5"],
                [0.70, "#D4D0FB"], [0.85, "#B3ACFA"], [1.0, "#968DF8"]],
    colors=_LIGHT_COLORS,
)
MODES = {"light": LIGHT, "dark": DARK}

# Kept for the Step 7 preview page.
COLORS = _DARK_COLORS
SECTOR_COLORS = {s: DARK.color(s) for s in [*_SECTOR_HUES, UNCLASSIFIED_EQUITY]}

# --------------------------------------------------------------------------- Plotly templates


def _template(m: Mode) -> go.layout.Template:
    return go.layout.Template(
        layout=dict(
            font=dict(family=FONT, size=13, color=m.ink),
            title=dict(font=dict(family=FONT, size=18, color=m.ink), x=0, xanchor="left"),
            paper_bgcolor=m.panel,
            plot_bgcolor=m.panel,
            colorway=[m.colors[k] for k in ("violet", "green", "pink", "amber", "navy", "coral")],
            margin=dict(l=8, r=16, t=16, b=8),
            xaxis=dict(gridcolor=m.grid, zeroline=False, linecolor=m.grid, tickfont=dict(color=m.muted), ticks="",
                       automargin=True),
            yaxis=dict(gridcolor=m.grid, zeroline=False, linecolor=m.grid, tickfont=dict(color=m.ink), ticks="",
                       automargin=True),
            hoverlabel=dict(bgcolor=m.hover_bg, bordercolor=m.panel_line, font=dict(family=FONT, color=m.ink, size=13)),
            legend=dict(font=dict(color=m.ink_2), orientation="h", y=-0.08, x=0, bgcolor="rgba(0,0,0,0)"),
            barcornerradius=4,
            bargap=0.35,
        )
    )


for _m in MODES.values():
    pio.templates[_m.template] = _template(_m)

# --------------------------------------------------------------------------- CSS


def _vars(m: Mode) -> str:
    return (f"--hmp-shell:{m.shell};--hmp-panel:{m.panel};--hmp-line:{m.panel_line};--hmp-ink:{m.ink};"
            f"--hmp-ink-2:{m.ink_2};--hmp-muted:{m.muted};--hmp-grid:{m.grid};")


FONT_URL = "https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap"

CSS = f"""
<style>
@import url('{FONT_URL}');

/* Light by default; dark when the system asks for it. Each chart is drawn twice
   (containers keyed chart-light-* / chart-dark-*) and only the matching one shows. */
:root {{ {_vars(LIGHT)} }}
[class*="st-key-chart-dark"] {{ display: none; }}
@media (prefers-color-scheme: dark) {{
  :root {{ {_vars(DARK)} }}
  [class*="st-key-chart-dark"] {{ display: block; }}
  [class*="st-key-chart-light"] {{ display: none; }}
}}

html, body, .stMarkdown, .stTextArea textarea, .stButton button {{
  font-family: {FONT};
}}
.stApp {{ background: var(--hmp-shell); color: var(--hmp-ink); }}
header[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {{ display: none; }}
.block-container {{ max-width: 1180px; padding-top: 2.5rem; padding-bottom: 4rem; }}

/* Hero */
.hmp-hero {{ text-align: center; padding: 1.5rem 0 1.25rem; }}
.hmp-pill {{
  display: inline-block; padding: .35rem .9rem; border: 1px solid {VIOLET};
  border-radius: 999px; color: var(--hmp-ink); font-size: .85rem; margin-bottom: 1rem;
}}
.hmp-hero h1 {{
  color: var(--hmp-ink); font-weight: 700; font-size: clamp(2.2rem, 5vw, 3.6rem);
  line-height: 1.08; letter-spacing: -.02em; margin: 0 0 .75rem;
}}
.hmp-hero p {{ color: var(--hmp-ink-2); font-size: 1.1rem; max-width: 40rem; margin: 0 auto; }}
.hmp-byline {{ color: var(--hmp-muted); font-size: .88rem; margin-top: 1rem; }}
.hmp-byline b {{ color: var(--hmp-ink); font-weight: 600; }}
.hmp-byline a, .hmp-footer a {{ color: inherit; text-decoration: underline; text-underline-offset: 2px; }}
.hmp-byline a:hover, .hmp-footer a:hover {{ color: var(--hmp-ink); }}

/* Section headings */
.hmp-h2 {{ color: var(--hmp-ink); font-weight: 700; font-size: 1.6rem; margin: 2.5rem 0 .25rem; }}
.hmp-sub {{ color: var(--hmp-ink-2); font-size: .95rem; margin: 0 0 1rem; }}

/* Headline number cards */
.hmp-cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; }}
.hmp-card {{
  background: var(--hmp-panel); border: 1px solid var(--hmp-line); border-radius: 16px; padding: 1.1rem 1.25rem;
}}
.hmp-card .label {{ color: var(--hmp-ink-2); font-size: .8rem; text-transform: uppercase; letter-spacing: .06em; }}
.hmp-card .value {{ color: var(--hmp-ink); font-size: 2.1rem; font-weight: 700; line-height: 1.15; margin-top: .3rem; }}
.hmp-card .note {{ color: var(--hmp-ink-2); font-size: .85rem; margin-top: .2rem; }}
.hmp-card.accent {{ border-color: {VIOLET}; box-shadow: 0 0 0 1px {VIOLET} inset; }}

/* Chart panels: any container created with key="panel-..." */
[class*="st-key-panel"] {{
  background: var(--hmp-panel); border-radius: 18px; padding: 1.25rem 1.25rem 1.1rem;
  border: 1px solid var(--hmp-line);
}}
[class*="st-key-panel"] h3, [class*="st-key-panel"] p, [class*="st-key-panel"] li,
[class*="st-key-panel"] [data-testid="stCaptionContainer"] {{ color: var(--hmp-ink); }}
[class*="st-key-panel"] h3 {{ font-weight: 700; font-size: 1.25rem; margin: 0 0 .1rem; }}
.hmp-caption {{ color: var(--hmp-muted) !important; font-size: .82rem; }}
[class*="st-key-panel"] [data-testid="stExpander"] details {{ border-color: var(--hmp-grid); }}
[class*="st-key-panel"] [data-testid="stExpander"] summary p {{ color: var(--hmp-ink-2); }}

/* Buttons & inputs */
.stButton, .stFormSubmitButton {{ margin-top: 1rem; }}
.stButton > button, .stFormSubmitButton > button {{
  background: {VIOLET}; color: white; border: 0; border-radius: 999px;
  padding: .6rem 1.6rem; font-weight: 600;
}}
.stButton > button:hover, .stFormSubmitButton > button:hover {{ background: {VIOLET_HOVER}; color: white; }}
.stTextArea textarea {{
  background: var(--hmp-panel); color: var(--hmp-ink); border: 1px solid var(--hmp-line); border-radius: 12px;
  font-family: ui-monospace, Menlo, monospace !important;
}}
.stTextArea label p {{ color: var(--hmp-ink-2); }}

/* Summary, callouts, footer */
.hmp-summary-head {{ color: var(--hmp-ink); font-size: 1.15rem; font-weight: 600; margin: 0 0 .6rem; }}
.hmp-summary ul {{ margin: 0; padding-left: 1.1rem; }}
.hmp-summary li {{ color: var(--hmp-ink-2) !important; margin: .35rem 0; line-height: 1.5; }}
.hmp-callout {{
  border-left: 3px solid {VIOLET}; padding: .5rem .9rem; margin: .25rem 0 .75rem;
  color: var(--hmp-ink-2); font-size: .92rem; background: rgba(90, 84, 255, .08); border-radius: 0 10px 10px 0;
}}
.hmp-callout b {{ color: var(--hmp-ink); }}
.hmp-pairs {{ list-style: none; padding: 0 !important; margin: .25rem 0 0; width: 100% !important; display: block; }}
.hmp-pairs li {{ display: flex; justify-content: space-between; gap: 1rem; padding: .45rem 0; margin: 0 !important;
  border-bottom: 1px solid var(--hmp-grid); color: var(--hmp-ink-2) !important; }}
.hmp-pairs li b {{ color: var(--hmp-ink); font-variant-numeric: tabular-nums; }}
[class*="st-key-panel"] [data-testid="stMarkdownContainer"] {{ width: 100%; }}
.hmp-help {{ color: var(--hmp-ink-2); font-size: .9rem; line-height: 1.55; }}
.hmp-help code {{ color: var(--hmp-ink); background: rgba(90, 84, 255, .08); padding: .05rem .35rem; border-radius: 6px; }}
.hmp-footer {{ color: var(--hmp-muted); font-size: .8rem; text-align: center; margin-top: 3rem; line-height: 1.6; }}
[data-testid="stForm"] {{ border: 0; padding: 0; }}

/* Swatches (preview only) */
.hmp-swatches {{ display: flex; gap: 8px; flex-wrap: wrap; margin: .25rem 0 .75rem; }}
.hmp-swatch {{ width: 84px; font-size: .72rem; color: var(--hmp-ink-2); }}
.hmp-swatch div {{ height: 36px; border-radius: 8px; margin-bottom: 4px; }}
</style>
"""
