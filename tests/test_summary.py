import re

import numpy as np
import pandas as pd
import pytest

from portfolio.correlation import CorrResult, asset_correlation, sector_correlation
from portfolio.data import FixtureSource, Issue, load_market_data, parse_holdings
from portfolio.exposure import compute_exposure
from portfolio.summary import build_summary, pct, rho

TEST_PORTFOLIO = "SPY 20\nVOO 10\nQQQ 15\nAAPL 10\nNVDA 5\nIBIT 20\nJPM 8"
ADVICE_WORDS = re.compile(
    r"\b(buy|sell|reduce|increase|trim|rebalance|should|recommend|consider|avoid|overweight|underweight)\b", re.I
)
NUMBER = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")
STATIC_NUMBERS = {"10"}  # "top 10 holdings"


def run(text, source=None):
    holdings, issues = parse_holdings(text)
    md = load_market_data(holdings, source or FixtureSource())
    ex = compute_exposure(md)
    a, s = asset_correlation(md, ex), sector_correlation(md, ex)
    return md, ex, a, s, build_summary(ex, a, s, issues + md.issues)


@pytest.fixture(scope="module")
def result():
    return run(TEST_PORTFOLIO)


def test_every_number_in_text_comes_from_engine(result):
    *_, summary = result
    used = set(summary.numbers.values()) | STATIC_NUMBERS
    found = NUMBER.findall(summary.text)
    assert found, summary.text
    stray = [x for x in found if x not in used]
    assert stray == [], f"numbers not traced to engine: {stray}\n{summary.text}"


def test_numbers_match_engine_tables(result):
    md, ex, a, s, summary = result
    n = summary.numbers
    pos = ex.positions.set_index("ticker")["weight"]
    assert n["total_value"] == f"${ex.positions['value'].sum():,.0f}"
    assert n["largest_position_weight"] == pct(pos.max())
    sec = ex.sectors.query("kind == 'sector'").set_index("bucket")["weight"]
    assert n["largest_sector_weight"] == pct(sec.max())
    assert n["asset_pair_rho"] == rho(a.matrix.loc["SPY", "VOO"])
    co = ex.companies.set_index("symbol")
    assert n["company_0_total"] == pct(co.at["AAPL", "total"])
    assert n["company_0_direct"] == pct(co.at["AAPL", "direct"])


def test_test_portfolio_story(result):
    *_, summary = result
    t = summary.text
    assert summary.headline.startswith("7 positions worth $41,434")
    assert "The largest position is SPY at 36.9%" in t
    assert "Technology at 47.3%" in t and "treats as concentrated" not in t
    assert "AAPL is 7.9% held directly but 13.7% in total, because 3 funds also hold it." in t
    assert "NVDA is 2.7% held directly but 9.4% in total" in t
    assert "SPY and VOO are the most correlated holdings (1.00" in t and "move almost as one" in t
    assert "Communication Services and Consumer Discretionary are the most correlated" in t
    assert "Company-level figures cover 51.1% of the equity exposure" in t
    assert "unknown" not in t  # full asset-class and sector coverage


def test_no_advice_language(result):
    *_, summary = result
    assert not ADVICE_WORDS.search(summary.text), ADVICE_WORDS.search(summary.text)


def test_descriptive_only_across_portfolios():
    for text in ("AAPL 1", "SPY 1\nIBIT 50", "JPM 3\nAAPL 3\nNVDA 3", "QQQ 2\nVOO 2"):
        *_, summary = run(text)
        assert not ADVICE_WORDS.search(summary.text), summary.text


def test_single_holding():
    *_, summary = run("AAPL 1")
    assert summary.headline.startswith("1 position worth")
    assert "need at least two holdings" in summary.text
    assert "treats as concentrated" not in summary.text


def test_no_positive_pair_is_stated():
    _, ex, _, s, _ = run("AAPL 1\nJPM 1")
    neg = CorrResult(pd.DataFrame([[1.0, -0.4], [-0.4, 1.0]], index=["AAPL", "JPM"], columns=["AAPL", "JPM"]),
                     250, pd.Timestamp("2025-10-01"), pd.Timestamp("2026-09-29"))
    summary = build_summary(ex, neg, s)
    assert "No two holdings had a positive return correlation" in summary.text


def test_gaps_and_dropped_tickers_are_disclosed():
    class Partial(FixtureSource):
        def fund(self, t):  # QQQ look-through unavailable
            return None if t == "QQQ" else super().fund(t)

    md, ex, a, s, summary = run("SPY 1\nQQQ 1\nZZZZ 5", source=Partial())
    t = summary.text
    assert "has no asset-class or sector data and is shown as unknown" in t
    assert "Not included anywhere: ZZZZ" in t
    stray = [x for x in NUMBER.findall(t) if x not in set(summary.numbers.values()) | STATIC_NUMBERS]
    assert stray == []


def test_correlation_exclusions_are_disclosed():
    _, ex, a, s, _ = run("AAPL 1\nJPM 1")
    a.excluded = {"NEWCO": "only 20 daily returns (need 60)"}
    summary = build_summary(ex, a, s)
    assert "Left out of the correlations for lack of data: NEWCO." in summary.text
