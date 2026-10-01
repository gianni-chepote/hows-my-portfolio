import numpy as np
import pandas as pd
import pytest

from portfolio.correlation import (
    MIN_OBS,
    asset_correlation,
    correlation_matrix,
    daily_returns,
    sector_correlation,
    ranked_pairs,
    top_pair,
)
from portfolio.data import FixtureSource, load_market_data, parse_holdings
from portfolio.exposure import compute_exposure

TEST_PORTFOLIO = "SPY 20\nVOO 10\nQQQ 15\nAAPL 10\nNVDA 5\nIBIT 20\nJPM 8"


@pytest.fixture(scope="module")
def loaded():
    holdings, _ = parse_holdings(TEST_PORTFOLIO)
    md = load_market_data(holdings, FixtureSource())
    return md, compute_exposure(md)


def synthetic(n=250, seed=0, **series):
    """Price frame from return arrays; unspecified columns get random walks."""
    idx = pd.bdate_range("2025-10-01", periods=n + 1)
    rng = np.random.default_rng(seed)
    out = {}
    for name, rets in series.items():
        r = rng.normal(0, 0.01, n) if rets is None else np.asarray(rets, dtype=float)
        out[name] = 100 * np.concatenate([[1.0], np.cumprod(1 + r)])
    return pd.DataFrame(out, index=idx)


# --------------------------------------------------------------------------- test portfolio


def test_asset_matrix_shape_symmetry_diagonal(loaded):
    res = asset_correlation(*loaded)
    m = res.matrix
    assert res.ok and m.shape == (7, 7)
    assert list(m.columns) == list(loaded[1].positions["ticker"])
    assert np.allclose(m.values, m.values.T)
    assert np.allclose(np.diag(m.values), 1.0)
    assert ((m.values >= -1 - 1e-12) & (m.values <= 1 + 1e-12)).all()
    assert res.excluded == {}


def test_window_metadata(loaded):
    res = asset_correlation(*loaded)
    assert res.n_obs == 250
    assert res.start > pd.Timestamp("2025-09-29") and res.end == pd.Timestamp("2026-09-29")
    assert "250 obs" in res.window_label


def test_spy_voo_is_top_pair(loaded):
    a, b, rho = top_pair(asset_correlation(*loaded))
    assert {a, b} == {"SPY", "VOO"}
    assert rho > 0.99


def test_sector_matrix_uses_held_sectors_and_proxies(loaded):
    md, ex = loaded
    res = sector_correlation(md, ex)
    held = set(ex.sectors.query("kind == 'sector' and weight > 0")["bucket"])
    assert set(res.matrix.columns) == held
    assert res.proxies["Technology"] == "XLK"
    assert np.allclose(np.diag(res.matrix.values), 1.0)
    pair = top_pair(res)
    assert pair is not None and pair[0] != pair[1]


def test_sector_matrix_only_positive_exposure(loaded):
    md, _ = loaded
    holdings, _ = parse_holdings("AAPL 1\nJPM 1")
    ex = compute_exposure(load_market_data(holdings, FixtureSource()))
    res = sector_correlation(md, ex)
    assert set(res.matrix.columns) == {"Technology", "Financials"}


# --------------------------------------------------------------------------- method rules


def test_short_history_is_excluded_and_reported():
    prices = synthetic(A=None, B=None, C=None)
    prices.iloc[:-30, prices.columns.get_loc("C")] = np.nan  # only 30 prices
    res = correlation_matrix(prices)
    assert list(res.matrix.columns) == ["A", "B"]
    assert "C" in res.excluded and "need" in res.excluded["C"]
    assert res.n_obs == 250  # C's short history did not shrink the common window


def test_constant_returns_are_excluded():
    prices = synthetic(A=None, B=None, CASH=np.zeros(250))
    res = correlation_matrix(prices)
    assert "CASH" not in res.matrix.columns
    assert "constant" in res.excluded["CASH"]


def test_gaps_are_not_forward_filled():
    prices = synthetic(A=None, B=None)
    prices.iloc[100:110, 0] = np.nan  # 10 missing prices in A
    res = correlation_matrix(prices)
    # 10 missing days plus the day after the gap have no valid return.
    assert res.n_obs == 250 - 11


def test_gap_does_not_create_fake_return():
    prices = synthetic(A=np.full(250, 0.01), B=None)
    prices.iloc[100:110, 0] = np.nan
    rets = daily_returns(prices)["A"].dropna()
    assert np.allclose(rets, 0.01)  # no 11-day return disguised as one day


def test_no_positive_pair_returns_none():
    r = np.random.default_rng(1).normal(0, 0.01, 250)
    res = correlation_matrix(synthetic(A=r, B=-r))
    assert res.matrix.loc["A", "B"] == pytest.approx(-1.0)
    assert top_pair(res) is None


def test_top_pair_ignores_diagonal_and_picks_highest():
    rng = np.random.default_rng(2)
    base = rng.normal(0, 0.01, 250)
    prices = synthetic(A=base, B=base + rng.normal(0, 0.002, 250), C=rng.normal(0, 0.01, 250))
    a, b, rho = top_pair(correlation_matrix(prices))
    assert {a, b} == {"A", "B"} and 0.9 < rho < 1.0


def test_single_asset_has_no_matrix():
    res = correlation_matrix(synthetic(A=None))
    assert not res.ok and top_pair(res) is None


def test_too_few_overlapping_days():
    prices = synthetic(A=None, B=None)
    prices.iloc[: 250 - MIN_OBS + 10, 0] = np.nan  # A has MIN_OBS - 10 returns
    prices.iloc[250 - MIN_OBS + 20 :, 1] = np.nan
    res = correlation_matrix(prices)
    assert not res.ok
    assert res.window_label == "No overlapping history"


def test_lookback_trims_older_prices():
    prices = synthetic(n=600, A=None, B=None)
    res = correlation_matrix(prices)
    assert res.start >= prices.index.max() - pd.Timedelta(days=365)


def test_ranked_pairs_are_distinct_and_sorted(loaded):
    pairs = ranked_pairs(asset_correlation(*loaded))
    assert len(pairs) == 7 * 6 // 2
    assert all(a != b for a, b, _ in pairs)
    rhos = [r for *_, r in pairs]
    assert rhos == sorted(rhos, reverse=True)
    assert {pairs[0][0], pairs[0][1]} == {"SPY", "VOO"}
