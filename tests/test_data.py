import pandas as pd
import pytest

from portfolio.data import (
    SECTOR_PROXIES,
    FixtureSource,
    canonical_symbol,
    is_leveraged_or_inverse,
    load_market_data,
    parse_holdings,
    to_gics,
)

TEST_PORTFOLIO = """
SPY   20
VOO   10
QQQ   15
AAPL  10
NVDA   5
IBIT  20
JPM    8
"""


@pytest.fixture(scope="module")
def source():
    return FixtureSource()


# --------------------------------------------------------------------------- parsing


def test_parse_basic():
    df, issues = parse_holdings(TEST_PORTFOLIO)
    assert list(df["ticker"]) == ["SPY", "VOO", "QQQ", "AAPL", "NVDA", "IBIT", "JPM"]
    assert df["shares"].sum() == 88
    assert issues == []


def test_parse_merges_duplicates_and_keeps_order():
    df, issues = parse_holdings("aapl 10\nSPY 1\nAAPL 2.5")
    assert df.to_dict("records") == [{"ticker": "AAPL", "shares": 12.5}, {"ticker": "SPY", "shares": 1.0}]
    assert [i.level for i in issues] == ["info"]


def test_parse_fractional_and_separators():
    df, issues = parse_holdings("AAPL,0.25\nSPY\t3\nBRK.B ; 1.5")
    assert df.set_index("ticker")["shares"].to_dict() == {"AAPL": 0.25, "SPY": 3.0, "BRK-B": 1.5}
    assert issues == []


def test_parse_blank_lines_and_comments():
    df, issues = parse_holdings("\n\n# my portfolio\nSPY 1  # core\n\n")
    assert list(df["ticker"]) == ["SPY"]
    assert issues == []


@pytest.mark.parametrize(
    "line",
    ["AAPL", "AAPL 10 extra", "AAPL ten", "AAPL -5", "AAPL 0", "$$$ 5", "1ABC 5", "AAPL inf", "AAPL nan"],
)
def test_parse_bad_lines_are_errors(line):
    df, issues = parse_holdings(f"SPY 1\n{line}")
    assert list(df["ticker"]) == ["SPY"]
    assert len(issues) == 1 and issues[0].level == "error"
    assert "Line 2" in issues[0].message


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("TSLA", "TSLA has no share count. Add the number of shares after it, e.g. TSLA 10."),
        ("4", "4 has no ticker. Put the ticker first, e.g. AAPL 4."),
        ("AAPL 10 extra", "has too many values"),
    ],
)
def test_shape_errors_say_what_is_missing(text, fragment):
    _, issues = parse_holdings(text)
    assert len(issues) == 1 and fragment in issues[0].message


def test_ticker_and_shares_split_across_lines_get_one_message():
    df, issues = parse_holdings("SPY 1\ntsla\n4\nAAPL 2")
    assert list(df["ticker"]) == ["SPY", "AAPL"]  # nothing guessed into the portfolio
    assert [i.message for i in issues] == [
        "Line 2: TSLA has no share count and line 3 has no ticker. If you meant 4 shares of TSLA, "
        "enter TSLA 4 on one line."
    ]


def test_parse_empty_input():
    df, issues = parse_holdings("  \n# nothing\n")
    assert df.empty
    assert issues[0].level == "error"


# --------------------------------------------------------------------------- normalisation helpers


@pytest.mark.parametrize(
    "raw, label",
    [
        ("consumer_cyclical", "Consumer Discretionary"),
        ("Consumer Cyclical", "Consumer Discretionary"),
        ("financial_services", "Financials"),
        ("Financial Services", "Financials"),
        ("basic_materials", "Materials"),
        ("consumer_defensive", "Consumer Staples"),
        ("realestate", "Real Estate"),
        ("Real Estate", "Real Estate"),
        ("Technology", "Technology"),
        ("crypto", None),
        (None, None),
    ],
)
def test_to_gics(raw, label):
    assert to_gics(raw) == label


def test_every_yahoo_fund_key_maps(source):
    for fund in ("SPY", "VOO", "QQQ"):
        keys = source.fund(fund)["sector_weightings"]
        assert all(to_gics(k) for k in keys), fund


def test_canonical_symbol():
    assert canonical_symbol("GOOG") == "GOOGL"
    assert canonical_symbol("brk.a") == "BRK-B"
    assert canonical_symbol("AAPL") == "AAPL"


# --------------------------------------------------------------------------- load from fixtures


def test_load_test_portfolio(source):
    holdings, _ = parse_holdings(TEST_PORTFOLIO)
    md = load_market_data(holdings, source)

    assert md.issues == []
    assert len(md.quotes) == 7
    q = md.quotes.set_index("ticker")
    assert q.loc["JPM", "sector"] == "Financials"
    assert q.loc["AAPL", "sector"] == "Technology"
    assert pd.isna(q.loc["SPY", "sector"])
    assert q.loc["IBIT", "category"] == "Digital Assets"
    assert (q["currency"] == "USD").all()
    assert md.as_of is not None and md.as_of.tzinfo is not None

    # Sector weights: 11 GICS labels per equity fund, each sleeve sums to ~100%.
    sums = md.fund_sectors.groupby("fund")["weight"].sum()
    assert set(sums.index) == {"SPY", "VOO", "QQQ"}
    assert sums.between(0.99, 1.01).all()
    assert md.fund_sectors["sector"].notna().all()

    # IBIT has asset classes but no sectors or holdings.
    ibit = md.fund_assets.query("fund == 'IBIT'").set_index("asset_class")["weight"]
    assert ibit["otherPosition"] == 1.0
    assert "IBIT" not in set(md.fund_holdings["fund"])

    # Prices: every holding plus every sector proxy, 1y, no gaps.
    assert list(md.prices.columns) == list(q.index) + list(SECTOR_PROXIES.values())
    assert len(md.prices) >= 250
    assert md.prices.notna().all().all()


def test_share_classes_merge_in_fund_holdings(source):
    holdings, _ = parse_holdings("SPY 1")
    md = load_market_data(holdings, source)
    spy = md.fund_holdings.set_index("symbol")["weight"]
    assert "GOOG" not in spy.index
    raw = {h["symbol"]: h["weight"] for h in source.fund("SPY")["top_holdings"]}
    assert spy["GOOGL"] == pytest.approx(raw["GOOGL"] + raw["GOOG"])
    assert spy.sum() == pytest.approx(sum(raw.values()))


def test_unknown_ticker_is_reported_not_dropped_silently(source):
    holdings, _ = parse_holdings("SPY 1\nZZZZ 3")
    md = load_market_data(holdings, source)
    assert list(md.quotes["ticker"]) == ["SPY"]
    assert [(i.level, i.ticker) for i in md.issues] == [("error", "ZZZZ")]


class _StubSource:
    """Lets tests shape quotes the fixtures don't contain."""

    def __init__(self, quotes, funds=None, history=True):
        self._q, self._f, self._history = quotes, funds or {}, history

    def quote(self, t):
        return self._q.get(t)

    def fund(self, t):
        return self._f.get(t)

    def prices(self, tickers):
        if not self._history:
            return pd.DataFrame(columns=tickers)
        dates = pd.bdate_range("2026-01-02", periods=5, name="date")
        return pd.DataFrame({t: [10.0, 10.1, 10.0, 10.2, 10.3] for t in tickers}, index=dates)


def _q(**kw):
    base = {"quoteType": "EQUITY", "regularMarketPrice": 10.0, "currency": "USD",
            "regularMarketTime": 1790712000, "sector": "Technology"}
    return base | kw


@pytest.mark.parametrize(
    "quote, level, fragment",
    [
        (_q(regularMarketPrice=None), "error", "no price"),
        (_q(currency="EUR"), "error", "EUR"),
        (_q(quoteType="MUTUALFUND"), "error", "not supported"),
        (_q(sector=None), "warning", "no sector"),
    ],
)
def test_quote_problems_surface_as_issues(quote, level, fragment):
    md = load_market_data(pd.DataFrame({"ticker": ["X"], "shares": [1.0]}), _StubSource({"X": quote}))
    assert len(md.issues) == 1
    assert md.issues[0].level == level and fragment in md.issues[0].message
    assert len(md.quotes) == (1 if level == "warning" else 0)


def test_etf_without_fund_data_is_flagged():
    src = _StubSource({"E": _q(quoteType="ETF", sector=None)})
    md = load_market_data(pd.DataFrame({"ticker": ["E"], "shares": [1.0]}), src)
    assert len(md.quotes) == 1
    assert md.issues[0].level == "warning" and "look-through" in md.issues[0].message


def _holdings(*tickers):
    return pd.DataFrame({"ticker": list(tickers), "shares": [1.0] * len(tickers)})


@pytest.mark.parametrize(
    "category, name",
    [
        ("Trading--Leveraged Equity", "ProShares UltraPro QQQ"),
        ("Trading--Inverse Equity", "ProShares Short S&P500"),
        ("Trading--Miscellaneous", "ProShares Ultra VIX Short-Term Futures ETF"),
        (None, "Direxion Daily 20+ Year Treasury Bull 3X Shares"),
        (None, "AdvisorShares Ranger Equity Bear ETF"),
    ],
)
def test_leveraged_and_inverse_funds_are_excluded(category, name):
    src = _StubSource({"L": _q(quoteType="ETF", sector=None, category=category, longName=name)})
    md = load_market_data(_holdings("L"), src)
    assert md.quotes.empty
    assert len(md.issues) == 1
    assert md.issues[0].level == "error" and "leveraged or inverse" in md.issues[0].message


@pytest.mark.parametrize(
    "category, name",
    [
        ("Ultrashort Bond", "JPMorgan Ultra-Short Income ETF"),
        ("Short Government", "iShares Short Treasury Bond ETF"),
        ("Derivative Income", "JPMorgan Equity Premium Income ETF"),
        ("Large Growth", "Invesco QQQ Trust"),
    ],
)
def test_ordinary_funds_are_not_flagged_as_leveraged(category, name):
    assert not is_leveraged_or_inverse(category, name)


def test_provider_outage_is_one_clear_message():
    md = load_market_data(_holdings("SPY", "AAPL", "QQQ"), _StubSource({}))
    assert md.quotes.empty
    assert len(md.issues) == 1
    assert "Yahoo Finance is not responding" in md.issues[0].message


def test_all_bad_tickers_while_provider_is_up_are_listed_individually():
    md = load_market_data(_holdings("ZZZZ", "QQQQQ"), _StubSource({"SPY": _q()}))
    assert [i.ticker for i in md.issues] == ["ZZZZ", "QQQQQ"]
    assert all("ticker not found" in i.message for i in md.issues)


def test_missing_price_history_is_reported():
    md = load_market_data(_holdings("X"), _StubSource({"X": _q()}, history=False))
    assert len(md.quotes) == 1
    assert len(md.issues) == 1
    assert md.issues[0].level == "warning" and "Price history is unavailable" in md.issues[0].message
