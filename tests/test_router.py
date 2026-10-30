import pytest

from master_agent.router import route


@pytest.mark.parametrize("q,mode", [
    ("TRANSRAIL fundamentals", "A"),
    ("TRANSRAIL technicals", "B"),
    ("TRANSRAIL complete analysis", "C"),
    ("Show me ROCE, ROE and debt-to-equity", "D"),
    ("Give me only EMA 21, 63 and 200", "D"),
    ("compare TCS vs INFY", "E"),
    ("TRANSRAIL positional trading", "F"),
    ("Is TRANSRAIL overvalued?", "V"),
    ("Compare my portfolio with Motilal Oswal Small Cap Fund", "P"),
    ("Give me a quick update", "Q"),
    ("TRANSRAIL last three quarterly results", "D"),
])
def test_modes(q, mode):
    assert route(q)["mode"] == mode


def test_selective_mode_lists_only_requested_metrics():
    r = route("Show me ROCE, ROE and debt-to-equity", "TCS")
    assert r["fund_metrics"] == ["ROCE", "ROE", "Debt-to-Equity"]
    assert "chart" not in r["sections"]
    assert r["symbols"] == ["TCS"]


def test_support_resistance_question_gets_levels_and_chart():
    r = route("what are the support and resistance levels", "RELIANCE")
    assert r["mode"] == "D" and "levels" in r["sections"] and "chart" in r["sections"]
