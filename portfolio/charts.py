"""Plotly figure builders. Take engine tables, return themed figures.

No Streamlit here: the app decides where each figure goes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from portfolio import theme
from portfolio.correlation import CorrResult

_BAR_HEIGHT = 34  # px per bar row, so ranked bars never get cramped


def donut(asset_classes: pd.DataFrame, total_value: float, title_center: str = "Total", mode: str = "dark") -> go.Figure:
    """Asset-class donut in fixed ASSET_ORDER; zero slices dropped."""
    m = theme.MODES[mode]
    df = asset_classes.set_index("asset_class").reindex(theme.ASSET_ORDER).fillna(0.0)
    df = df[df["weight"] > 0.0005]
    fig = go.Figure(
        go.Pie(
            labels=[f"{c}  {w:.1%}" for c, w in zip(df.index, df["weight"])],  # factsheet-style legend
            values=df["weight"],
            customdata=df["value"],
            hole=0.64,
            sort=False,
            direction="clockwise",
            rotation=90,
            marker=dict(colors=[m.color(c) for c in df.index], line=dict(color=m.panel, width=2)),
            textinfo="none",
            hovertemplate="<b>%{label}</b><br>$%{customdata:,.0f}<extra></extra>",
        )
    )
    fig.update_layout(
        template=m.template,
        paper_bgcolor=m.panel,  # set explicitly: Streamlit overrides template backgrounds
        plot_bgcolor=m.panel,
        height=380,
        showlegend=True,
        legend=dict(orientation="v", x=1.02, y=0.5, yanchor="middle"),
        margin=dict(l=24, r=24, t=24, b=24),
        annotations=[
            dict(text=f"<span style='font-size:13px;color:{m.muted}'>{title_center}</span><br>"
                      f"<b>${total_value:,.0f}</b>",
                 showarrow=False, font=dict(size=22, color=m.ink), x=0.5, y=0.5, xref="paper", yref="paper")
        ],
    )
    return fig


def ranked_bars(
    labels: list[str],
    weights: list[float],
    colors: list[str] | str,
    hover_extra: list[str] | None = None,
    sort: bool = True,
    mode: str = "dark",
) -> go.Figure:
    """Horizontal bars, % labels at the bar end. Largest on top unless sort=False (keeps given order)."""
    m = theme.MODES[mode]
    order = np.argsort(weights, kind="stable") if sort else np.arange(len(weights))[::-1]  # plotly draws bottom-up
    labels = [labels[i] for i in order]
    weights = [weights[i] for i in order]
    colors = colors if isinstance(colors, str) else [colors[i] for i in order]
    extra = [hover_extra[i] for i in order] if hover_extra else [""] * len(labels)
    xmax = max(weights) if weights else 1
    fig = go.Figure(
        go.Bar(
            y=labels, x=weights, orientation="h",
            marker=dict(color=colors),
            text=[f"{w:.1%}" for w in weights],
            textposition="outside",
            textfont=dict(color=m.ink_2, size=12),
            cliponaxis=False,
            customdata=extra,
            hovertemplate="<b>%{y}</b><br>%{x:.1%} of portfolio%{customdata}<extra></extra>",
        )
    )
    fig.update_layout(
        template=m.template,
        paper_bgcolor=m.panel,  # set explicitly: Streamlit overrides template backgrounds
        plot_bgcolor=m.panel,
        height=max(160, _BAR_HEIGHT * len(labels) + 50),
        xaxis=dict(tickformat=".0%", range=[0, xmax * 1.18], showgrid=True),
        yaxis=dict(showgrid=False, ticksuffix="  "),
        showlegend=False,
    )
    return fig


def company_bars(companies: pd.DataFrame, top: int = 10, mode: str = "dark") -> go.Figure:
    """Stacked bars: direct ownership vs held through funds."""
    m = theme.MODES[mode]
    df = companies.head(top).iloc[::-1]
    direct = df["direct"] if "direct" in df else pd.Series(0.0, index=df.index)
    via = df["total"] - direct
    via_cols = [c for c in df.columns if c.startswith("via ")]
    breakdown = [
        "<br>".join(f"{c[4:]}: {row[c]:.1%}" for c in via_cols if row[c] > 0) or "—"
        for _, row in df.iterrows()
    ]
    fig = go.Figure()
    fig.add_bar(
        y=df["symbol"], x=direct, orientation="h", name="Held directly",
        marker=dict(color=m.colors["violet"], line=dict(color=m.panel, width=2)),
        hovertemplate="<b>%{y}</b><br>Direct: %{x:.1%}<extra></extra>",
    )
    fig.add_bar(
        y=df["symbol"], x=via, orientation="h", name="Through funds",
        marker=dict(color=m.colors["lavender"], line=dict(color=m.panel, width=2)),
        customdata=breakdown,
        text=[f"{t:.1%}" for t in df["total"]], textposition="outside", cliponaxis=False,
        textfont=dict(color=m.ink_2, size=12),
        hovertemplate="<b>%{y}</b><br>Through funds: %{x:.1%}<br>%{customdata}<extra></extra>",
    )
    fig.update_layout(
        template=m.template,
        paper_bgcolor=m.panel,  # set explicitly: Streamlit overrides template backgrounds
        plot_bgcolor=m.panel,
        barmode="stack",
        height=max(200, _BAR_HEIGHT * len(df) + 80),
        xaxis=dict(tickformat=".0%", range=[0, float(df["total"].max()) * 1.2]),
        yaxis=dict(showgrid=False, ticksuffix="  "),
        legend=dict(orientation="h", y=1.02, x=0, yanchor="bottom", traceorder="normal"),
        margin=dict(l=8, r=16, t=40, b=8),
    )
    return fig


def heatmap(res: CorrResult, mode: str = "dark") -> go.Figure:
    """Each distinct pair once: lower triangle without the diagonal (self-correlation is always 1)."""
    m = theme.MODES[mode]
    mat = res.matrix
    rows, cols = list(mat.index[1:]), list(mat.columns[:-1])
    z = mat.loc[rows, cols].values.copy()
    z[np.triu_indices_from(z, k=1)] = np.nan
    text = np.where(np.isnan(z), "", np.vectorize(lambda v: f"{v:.2f}")(np.nan_to_num(z)))
    n = len(rows)
    fig = go.Figure(
        go.Heatmap(
            z=z, x=cols, y=rows, zmin=-1, zmax=1, colorscale=m.corr_scale,
            text=text, texttemplate="%{text}", textfont=dict(size=12 if n <= 7 else 11, color=m.heat_text),
            xgap=3, ygap=3, hoverongaps=False,
            colorbar=dict(title=dict(text="ρ", side="top"), thickness=10, len=0.8, tickvals=[-1, -0.5, 0, 0.5, 1],
                          tickfont=dict(color=m.muted), outlinewidth=0),
            hovertemplate="<b>%{y} · %{x}</b><br>correlation %{z:.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        template=m.template,
        paper_bgcolor=m.panel,  # set explicitly: Streamlit overrides template backgrounds
        plot_bgcolor=m.panel,
        height=max(340, 52 * n + 150),
        xaxis=dict(showgrid=False, tickangle=-35, side="bottom"),
        yaxis=dict(showgrid=False, autorange="reversed", ticksuffix="  "),
        margin=dict(l=8, r=8, t=8, b=8),
    )
    return fig
