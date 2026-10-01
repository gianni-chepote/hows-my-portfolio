import pandas as pd
import pytest

from portfolio.data import FixtureSource, MarketData, load_market_data, parse_holdings
from portfolio.exposure import (
    CASH,
    COMMODITIES,
    CRYPTO,
    EQUITY,
    UNCLASSIFIED_EQUITY,
    UNKNOWN,
    compute_exposure,
)

TEST_PORTFOLIO = "SPY 20\nVOO 10\nQQQ 15\nAAPL 10\nNVDA 5\nIBIT 20\nJPM 8"


def make_md(quotes, fund_sectors=(), fund_assets=(), fund_holdings=()):
    """Hand-built MarketData. quotes: (ticker, shares, price, type, sector, category)."""
    q = pd.DataFrame(
        [
            {"ticker": t, "shares": sh, "name": t, "quote_type": qt, "price": px, "currency": "USD",
             "price_time": pd.Timestamp("2026-09-29", tz="UTC"), "sector": sec, "category": cat}
            for t, sh, px, qt, sec, cat in quotes
        ]
    )
    return MarketData(
        quotes=q,
        fund_sectors=pd.DataFrame(list(fund_sectors), columns=["fund", "sector", "weight"]),
        fund_assets=pd.DataFrame(list(fund_assets), columns=["fund", "asset_class", "weight"]),
        fund_holdings=pd.DataFrame(list(fund_holdings), columns=["fund", "symbol", "name", "weight"]),
        prices=pd.DataFrame(),
    )


def sector(ex, bucket):
    return ex.sectors.set_index("bucket").at[bucket, "weight"]


def asset(ex, cls):
    return ex.asset_classes.set_index("asset_class").at[cls, "weight"]


@pytest.fixture(scope="module")
def ex():
    holdings, _ = parse_holdings(TEST_PORTFOLIO)
    return compute_exposure(load_market_data(holdings, FixtureSource()))


# --------------------------------------------------------------------------- acceptance checks (brief)


def test_weights_sum_to_one(ex):
    assert ex.positions["weight"].sum() == pytest.approx(1.0)
    assert ex.positions["value"].sum() == pytest.approx(ex.total_value)


def test_asset_classes_and_sector_buckets_sum_to_one(ex):
    assert ex.asset_classes["weight"].sum() == pytest.approx(1.0)
    assert ex.sectors["weight"].sum() == pytest.approx(1.0, abs=1e-4)
    assert ex.sectors["value"].sum() == pytest.approx(ex.total_value, rel=1e-4)


def test_20pct_etf_at_40pct_tech_adds_8pp():
    md = make_md(
        [("ETF1", 2, 10.0, "ETF", None, "Large Blend"), ("BANK", 8, 10.0, "EQUITY", "Financials", None)],
        fund_sectors=[("ETF1", "Technology", 0.4), ("ETF1", "Healthcare", 0.6)],
        fund_assets=[("ETF1", "stockPosition", 1.0)],
    )
    ex = compute_exposure(md)
    assert sector(ex, "Technology") == pytest.approx(0.08)
    assert sector(ex, "Healthcare") == pytest.approx(0.12)
    assert sector(ex, "Financials") == pytest.approx(0.80)


def test_direct_and_fund_ownership_combine_without_double_counting(ex):
    pos = ex.positions.set_index("ticker")["weight"]
    co = ex.companies.set_index("symbol")
    via_cols = [c for c in co.columns if c.startswith("via ")]

    aapl = co.loc["AAPL"]
    assert aapl["direct"] == pytest.approx(pos["AAPL"])
    assert aapl["total"] == pytest.approx(aapl["direct"] + aapl[via_cols].sum())
    assert aapl["n_sources"] == 4  # direct + SPY + VOO + QQQ

    # Look-through never exceeds what the funds are worth, and nothing is counted twice:
    # named companies + undisclosed remainder == total equity exposure.
    assert co[via_cols].sum().sum() <= pos[["SPY", "VOO", "QQQ"]].sum()
    assert co["total"].sum() + ex.coverage["equity_undisclosed"] == pytest.approx(asset(ex, EQUITY))


# --------------------------------------------------------------------------- test-portfolio story


def test_aapl_and_nvda_exposure_exceeds_direct_position(ex):
    co = ex.companies.set_index("symbol")
    for sym in ("AAPL", "NVDA"):
        assert co.at[sym, "total"] > co.at[sym, "direct"] * 1.2, sym


def test_ibit_is_crypto_and_fund_cash_is_cash(ex):
    pos = ex.positions.set_index("ticker")["weight"]
    assert asset(ex, CRYPTO) == pytest.approx(pos["IBIT"])
    assert sector(ex, CRYPTO) == pytest.approx(pos["IBIT"])
    assert asset(ex, CASH) > 0
    assert asset(ex, UNKNOWN) == pytest.approx(0.0, abs=1e-3)


def test_alphabet_share_classes_are_one_company(ex):
    symbols = set(ex.companies["symbol"])
    assert "GOOGL" in symbols and "GOOG" not in symbols


def test_positions_sorted_and_labelled(ex):
    assert ex.positions["value"].is_monotonic_decreasing
    assert set(ex.positions["wrapper"]) == {"Stock", "ETF"}


def test_concentration(ex):
    c = ex.concentration
    assert c["n_positions"] == 7
    assert c["largest_position"] == ex.positions.at[0, "ticker"]
    assert 1 <= c["effective_positions"] <= 7
    assert c["largest_sector"] == "Technology"
    assert c["largest_company"] == "AAPL"  # 10 direct shares at ~$329 outweigh NVDA


def test_coverage(ex):
    cov = ex.coverage
    assert cov["asset_class_known"] == pytest.approx(1.0, abs=1e-3)
    assert cov["sector_known"] == pytest.approx(1.0, abs=1e-3)
    assert 0.3 < cov["equity_named"] < 0.8  # top-10 holdings only


# --------------------------------------------------------------------------- edge cases


def test_share_class_merge_across_direct_and_fund():
    md = make_md(
        [("GOOG", 1, 50.0, "EQUITY", "Communication Services", None), ("F", 1, 50.0, "ETF", None, "Large Blend")],
        fund_sectors=[("F", "Communication Services", 1.0)],
        fund_assets=[("F", "stockPosition", 1.0)],
        fund_holdings=[("F", "GOOGL", "Alphabet", 0.1)],
    )
    co = compute_exposure(md).companies.set_index("symbol")
    assert list(co.index) == ["GOOGL"]
    assert co.at["GOOGL", "total"] == pytest.approx(0.5 + 0.05)


def test_etf_without_fund_data_is_unknown_not_zero():
    md = make_md([("MYST", 1, 100.0, "ETF", None, "Large Blend"), ("AAPL", 1, 100.0, "EQUITY", "Technology", None)])
    ex = compute_exposure(md)
    assert asset(ex, UNKNOWN) == pytest.approx(0.5)
    assert sector(ex, UNKNOWN) == pytest.approx(0.5)
    assert ex.coverage["sector_known"] == pytest.approx(0.5)


def test_stock_without_sector_is_unclassified_equity():
    md = make_md([("XYZ", 1, 10.0, "EQUITY", None, None)])
    ex = compute_exposure(md)
    assert sector(ex, UNCLASSIFIED_EQUITY) == pytest.approx(1.0)
    assert ex.concentration["largest_sector"] is None


def test_fund_residual_asset_class_is_unknown_and_sectors_scale_by_equity_sleeve():
    md = make_md(
        [("F", 1, 100.0, "ETF", None, "Allocation")],
        fund_sectors=[("F", "Energy", 1.0)],
        fund_assets=[("F", "stockPosition", 0.6), ("F", "bondPosition", 0.3)],
    )
    ex = compute_exposure(md)
    assert asset(ex, EQUITY) == pytest.approx(0.6)
    assert asset(ex, "Fixed income") == pytest.approx(0.3)
    assert asset(ex, UNKNOWN) == pytest.approx(0.1)
    assert sector(ex, "Energy") == pytest.approx(0.6)  # not 1.0: bonds are not Energy
    assert ex.sectors["weight"].sum() == pytest.approx(1.0)


def test_commodity_category_overrides_other():
    md = make_md([("GLD", 1, 100.0, "ETF", None, "Commodities Focused")],
                 fund_assets=[("GLD", "otherPosition", 1.0)])
    assert asset(compute_exposure(md), COMMODITIES) == pytest.approx(1.0)


def test_partial_holdings_are_not_rescaled():
    md = make_md(
        [("F", 1, 100.0, "ETF", None, "Large Blend")],
        fund_sectors=[("F", "Technology", 1.0)],
        fund_assets=[("F", "stockPosition", 1.0)],
        fund_holdings=[("F", "AAA", "A", 0.2), ("F", "BBB", "B", 0.1)],
    )
    ex = compute_exposure(md)
    assert ex.companies["total"].sum() == pytest.approx(0.3)
    assert ex.coverage["equity_undisclosed"] == pytest.approx(0.7)


def test_empty_portfolio_raises():
    with pytest.raises(ValueError):
        compute_exposure(make_md([]))
