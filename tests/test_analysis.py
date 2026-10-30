import json

import numpy as np
import pandas as pd

from master_agent import positional, simulate, technical
from tests.conftest import frame


def test_full_technical_report_is_json_serialisable(range_bound):
    rep = technical.analyse(range_bound)
    json.dumps(rep)
    assert rep["ema"]["available"]
    assert set(rep["ema"]["values"]) == {"ema21", "ema63", "ema200"}
    assert rep["rsi"]["available"] and 0 <= rep["rsi"]["value"] <= 100
    assert not rep["delivery"]["available"]          # never invented
    assert rep["levels"]["immediate_support"]["level"] < rep["close"]


def test_short_history_says_cannot_confirm():
    df = frame(list(np.linspace(100, 110, 120)))
    rep = technical.analyse(df)
    assert not rep["ema"]["available"]
    p = positional.plan(df)
    assert p["verdict"] == positional.AVOID and not p["confirmed"]


def test_pullback_to_support_in_uptrend_gives_complete_plan(range_bound):
    df = range_bound.iloc[:-6].copy()   # last bar sits at the bottom of the range (~100)
    p = positional.plan(df)
    assert p["confirmed"]
    pl = p["pullback_plan"]
    assert pl["stop"] < pl["entry_zone"][0] <= pl["entry"] <= pl["entry_zone"][1]
    assert pl["t1"]["price"] > pl["entry"] and pl["t2"]["price"] >= pl["t1"]["price"]
    assert pl["rr_t1"] == round((pl["t1"]["price"] - pl["entry"]) / (pl["entry"] - pl["stop"]), 2)
    assert p["invalidation"] and p["risks"]


def test_downtrend_is_avoided():
    p = positional.plan(frame(list(np.linspace(200, 80, 300))))
    assert p["verdict"] == positional.AVOID


def test_hold_and_exit_for_existing_position(range_bound):
    up = frame(list(np.linspace(50, 150, 300)))
    assert positional.plan(up, position={"stop": 120})["verdict"] == positional.HOLD
    p = positional.plan(up, position={"stop": 155})
    assert p["verdict"] == positional.EXIT and "below stop" in p["invalidated_by"][0]
    # sideways range: price below EMA 63 invalidates the trade even above the stop
    p = positional.plan(range_bound, position={"stop": 90})
    assert p["verdict"] == positional.EXIT and "EMA 63" in p["invalidated_by"][0]


def test_simulation_runs_without_lookahead(range_bound):
    res = simulate.run({"AAA": range_bound}, start=str(range_bound.index[230].date()), capital=50_000)
    json.dumps(res, default=str)
    assert res["equity_curve"][0]["date"] >= str(range_bound.index[230].date())
    for t in res["closed_trades"]:
        assert t["exit_date"] >= t["entry_date"]
    # changing the future must not change past decisions
    cut = range_bound.iloc[:280]
    a = simulate.run({"AAA": cut}, start=str(range_bound.index[230].date()), capital=50_000)
    b = simulate.run({"AAA": range_bound}, start=str(range_bound.index[230].date()),
                     end=str(cut.index[-1].date()), capital=50_000)
    assert a["equity_curve"] == b["equity_curve"]


def test_flat_range_is_sideways_not_downtrend(range_bound):
    assert technical.analyse(range_bound)["trend"]["structure"].startswith("Equal highs and equal lows")
