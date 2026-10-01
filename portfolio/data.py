"""Data layer: parse user input, fetch market data, normalise it.

Everything downstream reads a `MarketData` object and never touches yfinance.
Two sources share one interface: `YahooSource` (live) and `FixtureSource`
(frozen snapshot in fixtures/, used by tests and offline demos).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

import pandas as pd

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

SECTORS = [
    "Technology", "Financials", "Healthcare", "Consumer Discretionary",
    "Communication Services", "Industrials", "Energy", "Materials",
    "Consumer Staples", "Utilities", "Real Estate",
]

# SPDR sector ETFs used as sector return proxies.
SECTOR_PROXIES = {
    "Technology": "XLK", "Financials": "XLF", "Healthcare": "XLV",
    "Consumer Discretionary": "XLY", "Communication Services": "XLC",
    "Industrials": "XLI", "Energy": "XLE", "Materials": "XLB",
    "Consumer Staples": "XLP", "Utilities": "XLU", "Real Estate": "XLRE",
}

# Yahoo sector names -> GICS-style labels. Keys are normalised by `_sector_key`,
# so both fund keys ("consumer_cyclical") and stock labels ("Consumer Cyclical") match.
_YAHOO_SECTORS = {
    "technology": "Technology",
    "financial_services": "Financials",
    "healthcare": "Healthcare",
    "consumer_cyclical": "Consumer Discretionary",
    "communication_services": "Communication Services",
    "industrials": "Industrials",
    "energy": "Energy",
    "basic_materials": "Materials",
    "consumer_defensive": "Consumer Staples",
    "utilities": "Utilities",
    "realestate": "Real Estate",
}

# Share classes of one issuer collapse onto a single symbol.
SHARE_CLASS_ALIASES = {"GOOG": "GOOGL", "BRK-A": "BRK-B", "FOX": "FOXA", "NWS": "NWSA"}

CRYPTO_CATEGORIES = {"Digital Assets"}

# Leveraged and inverse funds are out of scope (brief): Yahoo files them all under
# "Trading--..." categories; the name check catches any that slip through.
_TRADING_CATEGORY = "Trading--"
_LEVERAGED_NAME_RE = re.compile(r"\b\d(\.\d+)?x\b|\binverse\b|\bbear\b", re.IGNORECASE)

# Known-good symbol used to tell "every ticker is wrong" from "the provider is down".
_PROBE_TICKER = "SPY"

_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9\-]{0,9}$")


def _sector_key(name: str) -> str:
    key = name.strip().lower().replace(" ", "_")
    return "realestate" if key == "real_estate" else key


def to_gics(name: str | None) -> str | None:
    """Map a Yahoo sector name to a GICS-style label; None if unknown."""
    if not name:
        return None
    return _YAHOO_SECTORS.get(_sector_key(name))


def is_leveraged_or_inverse(category: str | None, name: str | None) -> bool:
    """True for leveraged, inverse, and other daily-reset trading funds."""
    if category and category.startswith(_TRADING_CATEGORY):
        return True
    return bool(name and _LEVERAGED_NAME_RE.search(name))


def canonical_symbol(symbol: str) -> str:
    """Yahoo form (BRK.B -> BRK-B) with share classes merged."""
    s = symbol.strip().upper().replace(".", "-")
    return SHARE_CLASS_ALIASES.get(s, s)


# --------------------------------------------------------------------------- input


@dataclass(frozen=True)
class Issue:
    level: str  # "error" | "warning" | "info"
    message: str
    ticker: str | None = None


def _is_number(token: str) -> bool:
    try:
        float(token)
    except ValueError:
        return False
    return True


def _shape_message(lineno: int, parts: list[str]) -> str:
    """Plain-English reason a line isn't 'TICKER SHARES'."""
    if len(parts) == 1 and _is_number(parts[0]):
        return f"Line {lineno}: {parts[0]} has no ticker. Put the ticker first, e.g. AAPL {parts[0]}."
    if len(parts) == 1:
        t = parts[0].upper()
        return f"Line {lineno}: {t} has no share count. Add the number of shares after it, e.g. {t} 10."
    return (f"Line {lineno}: '{' '.join(parts)}' has too many values. "
            "Use one ticker and one share count per line, e.g. AAPL 10.")


def parse_holdings(text: str) -> tuple[pd.DataFrame, list[Issue]]:
    """Parse 'TICKER SHARES' lines into a ticker/shares frame.

    Accepts spaces, tabs, or commas as separators, blank lines, and '#'
    comments. Duplicate tickers are merged. Bad lines become errors and are
    left out of the frame, so the caller can show them.
    """
    issues: list[Issue] = []
    rows: list[tuple[str, float]] = []
    lines = [(n, raw, [p for p in re.split(r"[\s,;]+", raw.split("#", 1)[0].strip()) if p])
             for n, raw in enumerate(text.splitlines(), start=1)]
    lines = [entry for entry in lines if entry[2]]
    skip_next = False
    for i, (lineno, raw, parts) in enumerate(lines):
        if skip_next:
            skip_next = False
            continue
        if len(parts) != 2:
            nxt = lines[i + 1][2] if i + 1 < len(lines) else None
            if len(parts) == 1 and nxt and len(nxt) == 1 and _is_number(nxt[0]) and not _is_number(parts[0]):
                # A ticker on one line and its share count on the next: one message for both.
                t, n = parts[0].upper(), nxt[0]
                issues.append(Issue("error", f"Line {lineno}: {t} has no share count and line {lines[i + 1][0]} "
                                             f"has no ticker. If you meant {n} shares of {t}, enter {t} {n} "
                                             "on one line.", t))
                skip_next = True
            else:
                issues.append(Issue("error", _shape_message(lineno, parts)))
            continue
        ticker = parts[0].upper().replace(".", "-")
        if not _TICKER_RE.match(ticker):
            issues.append(Issue("error", f"Line {lineno}: '{parts[0]}' is not a valid ticker.", parts[0]))
            continue
        try:
            shares = float(parts[1])
        except ValueError:
            issues.append(Issue("error", f"Line {lineno}: '{parts[1]}' is not a number of shares.", ticker))
            continue
        if not shares > 0 or shares == float("inf"):
            issues.append(Issue("error", f"Line {lineno}: shares must be positive (long-only).", ticker))
            continue
        rows.append((ticker, shares))

    df = pd.DataFrame(rows, columns=["ticker", "shares"])
    if df.empty:
        if not issues:
            issues.append(Issue("error", "Enter at least one holding."))
        return df, issues

    dupes = df["ticker"][df["ticker"].duplicated()].unique()
    for t in dupes:
        issues.append(Issue("info", f"{t} was entered more than once; shares were added together.", t))
    df = df.groupby("ticker", sort=False, as_index=False)["shares"].sum()
    return df, issues


# --------------------------------------------------------------------------- sources


class Source(Protocol):
    def quote(self, ticker: str) -> dict | None: ...
    def fund(self, ticker: str) -> dict | None: ...
    def prices(self, tickers: list[str]) -> pd.DataFrame: ...


class FixtureSource:
    """Serves the frozen snapshot in fixtures/. Unknown tickers return None."""

    def __init__(self, path: Path = FIXTURES):
        self._quotes = json.loads((path / "quotes.json").read_text())
        self._funds = json.loads((path / "funds.json").read_text())
        self._prices = pd.read_parquet(path / "prices_1y.parquet")

    def quote(self, ticker: str) -> dict | None:
        return self._quotes.get(ticker)

    def fund(self, ticker: str) -> dict | None:
        return self._funds.get(ticker)

    def prices(self, tickers: list[str]) -> pd.DataFrame:
        return self._prices.reindex(columns=tickers)


class YahooSource:
    """Live yfinance data in the same shape as the fixtures."""

    QUOTE_FIELDS = (
        "quoteType", "shortName", "longName", "regularMarketPrice", "currency",
        "regularMarketTime", "sector", "industry", "category",
    )

    def quote(self, ticker: str) -> dict | None:
        import yfinance as yf

        try:
            info = yf.Ticker(ticker).info or {}
        except Exception:  # noqa: BLE001 - yfinance raises many types for bad symbols
            return None
        if not info.get("quoteType"):
            return None
        return {k: info.get(k) for k in self.QUOTE_FIELDS}

    def fund(self, ticker: str) -> dict | None:
        import yfinance as yf

        try:
            fd = yf.Ticker(ticker).funds_data
            th = fd.top_holdings
            holdings = []
            if isinstance(th, pd.DataFrame) and not th.empty:
                holdings = [
                    {"symbol": str(sym), "name": row.get("Name"), "weight": float(row["Holding Percent"])}
                    for sym, row in th.iterrows()
                ]
            return {
                "sector_weightings": {k: float(v) for k, v in (fd.sector_weightings or {}).items()},
                "asset_classes": {k: float(v) for k, v in (fd.asset_classes or {}).items()},
                "top_holdings": holdings,
            }
        except Exception:  # noqa: BLE001
            return None

    def prices(self, tickers: list[str]) -> pd.DataFrame:
        import yfinance as yf

        if not tickers:
            return pd.DataFrame()
        try:
            raw = yf.download(tickers, period="1y", auto_adjust=True, progress=False)
        except Exception:  # noqa: BLE001
            return pd.DataFrame(columns=tickers)
        if raw.empty:
            return pd.DataFrame(columns=tickers)
        close = raw["Close"]
        if isinstance(close, pd.Series):
            close = close.to_frame(tickers[0])
        close.index = pd.to_datetime(close.index).tz_localize(None)
        close.index.name = "date"
        return close.reindex(columns=tickers)


# --------------------------------------------------------------------------- normalised data


@dataclass
class MarketData:
    """Normalised inputs for the calculation engine.

    quotes:        one row per usable holding; ticker, shares, name, quote_type,
                   price, currency, price_time, sector (GICS label), category
    fund_sectors:  fund, sector (GICS label), weight (share of the equity sleeve)
    fund_assets:   fund, asset_class, weight
    fund_holdings: fund, symbol (canonical), name, weight
    prices:        adjusted daily closes, columns = holdings + sector proxies
    issues:        everything the user should be told
    """

    quotes: pd.DataFrame
    fund_sectors: pd.DataFrame
    fund_assets: pd.DataFrame
    fund_holdings: pd.DataFrame
    prices: pd.DataFrame
    issues: list[Issue] = field(default_factory=list)

    @property
    def as_of(self) -> datetime | None:
        times = self.quotes["price_time"].dropna()
        return times.max().to_pydatetime() if not times.empty else None


def _to_utc(ts) -> pd.Timestamp | None:
    if isinstance(ts, (int, float)):
        return pd.Timestamp(datetime.fromtimestamp(ts, tz=timezone.utc))
    return None


def load_market_data(holdings: pd.DataFrame, source: Source) -> MarketData:
    """Fetch and normalise everything for the parsed holdings."""
    issues: list[Issue] = []
    quote_rows, sector_rows, asset_rows, holding_rows = [], [], [], []

    for ticker, shares in holdings[["ticker", "shares"]].itertuples(index=False):
        q = source.quote(ticker)
        if q is None:
            issues.append(Issue("error", f"{ticker}: ticker not found; it is excluded from all totals.", ticker))
            continue
        price = q.get("regularMarketPrice")
        if price is None or not price > 0:
            issues.append(Issue("error", f"{ticker}: no price available; it is excluded from all totals.", ticker))
            continue
        currency = q.get("currency")
        if currency != "USD":
            issues.append(
                Issue("error", f"{ticker}: quoted in {currency or 'unknown currency'}; v1 supports USD only.", ticker)
            )
            continue
        quote_type = q.get("quoteType")
        if quote_type not in ("EQUITY", "ETF"):
            issues.append(
                Issue("error", f"{ticker}: {quote_type} is not supported; v1 covers US stocks and ETFs.", ticker)
            )
            continue
        name = q.get("longName") or q.get("shortName") or ticker
        if quote_type == "ETF" and is_leveraged_or_inverse(q.get("category"), name):
            issues.append(Issue(
                "error",
                f"{ticker}: leveraged or inverse fund ({name}). This app does not model leverage or short "
                "exposure, so it is excluded from all totals.",
                ticker,
            ))
            continue

        sector = to_gics(q.get("sector")) if quote_type == "EQUITY" else None
        if quote_type == "EQUITY" and sector is None:
            issues.append(Issue("warning", f"{ticker}: no sector available; shown as unclassified.", ticker))

        quote_rows.append({
            "ticker": ticker,
            "shares": float(shares),
            "name": name,
            "quote_type": quote_type,
            "price": float(price),
            "currency": currency,
            "price_time": _to_utc(q.get("regularMarketTime")),
            "sector": sector,
            "category": q.get("category"),
        })

        if quote_type != "ETF":
            continue
        f = source.fund(ticker)
        if not f:
            issues.append(Issue("warning", f"{ticker}: fund look-through data unavailable; shown as unknown.", ticker))
            continue
        for key, w in f.get("sector_weightings", {}).items():
            label = to_gics(key)
            if label is None:
                issues.append(Issue("warning", f"{ticker}: unrecognised sector '{key}' treated as unknown.", ticker))
            sector_rows.append({"fund": ticker, "sector": label, "weight": float(w)})
        for cls, w in f.get("asset_classes", {}).items():
            asset_rows.append({"fund": ticker, "asset_class": cls, "weight": float(w)})
        for h in f.get("top_holdings", []):
            holding_rows.append({
                "fund": ticker,
                "symbol": canonical_symbol(h["symbol"]),
                "name": h.get("name"),
                "weight": float(h["weight"]),
            })

    not_found = [i for i in issues if i.message.endswith("ticker not found; it is excluded from all totals.")]
    if not quote_rows and len(not_found) == len(holdings) and source.quote(_PROBE_TICKER) is None:
        # Every lookup failed, including a symbol that always exists: the provider is down.
        issues = [Issue("error", "Yahoo Finance is not responding right now, so no prices could be loaded. "
                                 "Please try again in a few minutes.")]

    quotes = pd.DataFrame(quote_rows, columns=[
        "ticker", "shares", "name", "quote_type", "price", "currency", "price_time", "sector", "category",
    ])
    fund_sectors = pd.DataFrame(sector_rows, columns=["fund", "sector", "weight"])
    fund_assets = pd.DataFrame(asset_rows, columns=["fund", "asset_class", "weight"])
    fund_holdings = (
        pd.DataFrame(holding_rows, columns=["fund", "symbol", "name", "weight"])
        .groupby(["fund", "symbol"], as_index=False, sort=False)
        .agg(name=("name", "first"), weight=("weight", "sum"))
    )

    price_cols = list(quotes["ticker"]) + list(SECTOR_PROXIES.values())
    prices = source.prices(list(dict.fromkeys(price_cols)))
    if not quotes.empty and prices.reindex(columns=list(quotes["ticker"])).dropna(how="all").empty:
        issues.append(Issue("warning", "Price history is unavailable from Yahoo Finance right now, so the "
                                       "correlation heatmaps cannot be calculated. Values and exposures are unaffected."))

    return MarketData(quotes, fund_sectors, fund_assets, fund_holdings, prices, issues)
