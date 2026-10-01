"""Smoke tests: the whole page renders, offline, for good and bad input.

The app reads HMP_DATA=fixtures and serves the frozen snapshot, so these
run without the network. Tickers outside the snapshot count as not found.
"""

import pytest
from streamlit.testing.v1 import AppTest

APP = "streamlit_app.py"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("HMP_DATA", "fixtures")


def _run(text: str | None = None) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60).run()
    if text is not None:
        at.text_area[0].input(text)
        at.button[0].click().run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def _markdown(at: AppTest) -> str:
    return "\n".join(m.value for m in at.markdown)


def test_demo_portfolio_renders_every_section():
    at = _run()
    assert not at.error
    page = _markdown(at)
    for section in ("Portfolio value", "Allocation and sector exposure", "Underlying companies",
                    "How your holdings move together", "Summary"):
        assert section in page
    assert "&#36;41,434" in page
    # Positions, assets, sectors, companies, two heatmaps: each drawn once per colour mode.
    assert len(at.get("plotly_chart")) == 6 * 2


def test_bad_lines_and_unknown_tickers_warn_but_the_rest_renders():
    at = _run("SPY 10\nAAPL ten\nZZZZ 5\nAAPL 2\nAAPL 3")
    errors = [e.value for e in at.error]
    assert any("Line 2" in e for e in errors)
    assert any("ZZZZ" in e and "not found" in e for e in errors)
    assert any("shares were added together" in i.value for i in at.info)
    assert "Allocation and sector exposure" in _markdown(at)


def test_nothing_usable_stops_after_the_messages():
    at = _run("ZZZZ 5\nQQQQQ 1")
    assert len(at.error) == 2
    assert "Allocation and sector exposure" not in _markdown(at)


def test_empty_input_asks_for_a_holding():
    at = _run("   ")
    assert [e.value for e in at.error] == ["Enter at least one holding."]


def test_single_holding_explains_missing_correlations():
    at = _run("AAPL 3")
    assert not at.error
    assert "Correlations need at least two holdings" in _markdown(at)
