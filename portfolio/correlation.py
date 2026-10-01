"""Correlation engine: asset and sector heatmaps plus the most correlated pair.

Method (brief, "Methodology rules"):
- daily simple returns on adjusted closes, 1-year lookback, Pearson;
- one common window: every included series is aligned on the same dates;
- no forward-filling, so a missing price removes that day (and the next) rather
  than inventing a multi-day return;
- series with too little history or constant returns are excluded and reported.

Correlation measures past co-movement. It is not a forecast or a count of
independent risks.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from portfolio.data import SECTOR_PROXIES, MarketData
from portfolio.exposure import Exposure

LOOKBACK_DAYS = 365
MIN_OBS = 60


@dataclass
class CorrResult:
    matrix: pd.DataFrame                 # empty if fewer than two usable series
    n_obs: int
    start: pd.Timestamp | None
    end: pd.Timestamp | None
    excluded: dict[str, str] = field(default_factory=dict)  # label -> reason
    proxies: dict[str, str] = field(default_factory=dict)   # label -> ticker (sector view)

    @property
    def ok(self) -> bool:
        return self.matrix.shape[0] >= 2

    @property
    def window_label(self) -> str:
        if self.start is None:
            return "No overlapping history"
        return f"Daily returns {self.start:%d %b %Y} – {self.end:%d %b %Y} ({self.n_obs} obs)"


def daily_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Simple returns without filling gaps."""
    return prices.sort_index().pct_change(fill_method=None).iloc[1:]


def correlation_matrix(
    prices: pd.DataFrame, lookback_days: int = LOOKBACK_DAYS, min_obs: int = MIN_OBS
) -> CorrResult:
    """Pearson correlation of daily returns on one common window."""
    if prices.empty or prices.shape[1] == 0:
        return CorrResult(pd.DataFrame(), 0, None, None)

    prices = prices.sort_index()
    cutoff = prices.index.max() - pd.Timedelta(days=lookback_days)
    rets = daily_returns(prices.loc[prices.index >= cutoff])

    excluded: dict[str, str] = {}
    for col in rets.columns:
        n = int(rets[col].notna().sum())
        if n < min_obs:
            excluded[col] = f"only {n} daily returns (need {min_obs})"
    rets = rets.drop(columns=list(excluded))

    rets = rets.dropna(how="any")
    for col in rets.columns:
        if rets[col].std() == 0:
            excluded[col] = "constant returns, correlation undefined"
    rets = rets.drop(columns=[c for c in rets.columns if c in excluded])

    if rets.shape[1] < 2 or len(rets) < min_obs:
        if rets.shape[1] >= 2:
            for col in rets.columns:
                excluded[col] = f"only {len(rets)} overlapping daily returns (need {min_obs})"
        return CorrResult(pd.DataFrame(), len(rets), None, None, excluded)

    matrix = rets.corr(method="pearson")
    return CorrResult(matrix, len(rets), rets.index.min(), rets.index.max(), excluded)


def asset_correlation(md: MarketData, ex: Exposure) -> CorrResult:
    """Correlations of the securities as entered, ETFs on their own history."""
    tickers = list(ex.positions["ticker"])
    return correlation_matrix(md.prices.reindex(columns=tickers))


def sector_correlation(md: MarketData, ex: Exposure) -> CorrResult:
    """Correlations of SPDR sector proxies, for sectors the portfolio holds."""
    held = ex.sectors.query("kind == 'sector' and weight > 0").sort_values("weight", ascending=False)
    proxies = {s: SECTOR_PROXIES[s] for s in held["bucket"]}
    prices = md.prices.reindex(columns=list(proxies.values()))
    prices.columns = list(proxies)
    res = correlation_matrix(prices)
    res.proxies = proxies
    return res


def ranked_pairs(res: CorrResult) -> list[tuple[str, str, float]]:
    """Every distinct pair, most correlated first."""
    if not res.ok:
        return []
    m = res.matrix
    upper = m.where(np.triu(np.ones(m.shape, dtype=bool), k=1))
    pairs = upper.stack().dropna().sort_values(ascending=False)  # stack keeps NaN in pandas 3
    return [(a, b, float(r)) for (a, b), r in pairs.items()]


def top_pair(res: CorrResult) -> tuple[str, str, float] | None:
    """Highest positive correlation among distinct pairs; None if none is positive."""
    pairs = ranked_pairs(res)
    if not pairs or pairs[0][2] <= 0:
        return None
    return pairs[0]
