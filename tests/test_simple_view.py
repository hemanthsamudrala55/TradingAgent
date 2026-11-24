from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from conftest import frame
from master_agent import frames, positional as pos, robot
from master_agent.data import normalise_hourly

IST = timezone(timedelta(hours=5, minutes=30))


def enter_plan(entry=100.0, stop=95.0, target=110.0):
    return {"verdict": pos.ENTER, "confirmed": True,
            "plan": {"entry": entry, "stop": stop, "t1": {"price": target}}}


@pytest.fixture
def store(monkeypatch, tmp_path):
    monkeypatch.setattr(robot, "STATE_FILE", tmp_path / "robot.json")
    robot.update_settings({"stocks": ["AAA"], "money": 100000, "risk_pct": 1})


def daily_rows(rows, start="2026-01-05"):
    idx = pd.bdate_range(start, periods=len(rows))
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"], index=idx)


@pytest.mark.parametrize("name,periods,first_label", [("Month", 4, "Jan 2024"), ("Quarter", 2, "Q1 2024"),
                                                     ("Half-year", 1, "Jan-Jun 2024"), ("Year", 1, "2024")])
def test_resample_periods(name, periods, first_label):
    df = frame(list(range(100, 170)))     # 70 weekdays from 1 Jan 2024, into April
    out = frames.resample(df, name)
    assert len(out) == periods
    assert frames.label(out.index[0], name) == first_label


def test_resample_aggregates_ohlcv():
    df = daily_rows([(10, 12, 9, 11, 100), (11, 15, 10, 14, 200), (14, 14, 8, 9, 300)], "2026-03-30")
    q1, q2 = frames.resample(df, "Quarter").itertuples()
    assert (q1.open, q1.high, q1.low, q1.close, q1.volume) == (10, 15, 9, 14, 300)
    assert (q2.open, q2.close, q2.volume) == (14, 9, 300)


def test_hourly_keeps_indian_clock_time():
    raw = pd.DataFrame({"date": ["2026-10-30T09:15:00+05:30", "2026-10-30T10:15:00+05:30"], "open": [1, 2],
                        "high": [2, 3], "low": [1, 2], "close": [2, 3], "volume": [5, 6]})
    assert normalise_hourly(raw).index[0] == pd.Timestamp("2026-10-30 09:15")


def test_automatic_mode_is_refused(store):
    with pytest.raises(ValueError):
        robot.update_settings({"mode": "auto"})
    assert robot.load()["mode"] == "practice"


def test_practice_buy_is_sized_to_the_loss_limit(store):
    df = daily_rows([(100, 101, 99, 100, 1)])
    s = robot.check(lambda _: df, plan=lambda d: enter_plan())["state"]
    assert s["positions"][0]["qty"] == 200          # 1% of 100000 = 1000, at 5 per share


def test_buy_is_capped_by_available_money(store):
    robot.update_settings({"money": 1000})
    df = daily_rows([(100, 101, 99, 100, 1)])
    s = robot.check(lambda _: df, plan=lambda d: enter_plan(stop=99.99))["state"]
    assert s["positions"][0]["qty"] == 10


def test_each_candle_is_judged_once(store):
    df = daily_rows([(100, 101, 99, 100, 1)])
    calls = []
    plan = lambda d: calls.append(1) or {"verdict": pos.WAIT, "confirmed": True}
    robot.check(lambda _: df, plan=plan)
    robot.check(lambda _: df, plan=plan)
    assert len(calls) == 1


def test_stop_beats_target_when_one_candle_touches_both(store):
    entry_day = daily_rows([(100, 101, 99, 100, 1)])
    robot.check(lambda _: entry_day, plan=lambda d: enter_plan())
    later = daily_rows([(100, 101, 99, 100, 1), (100, 111, 94, 105, 1)])
    s = robot.check(lambda _: later, plan=lambda d: {"verdict": pos.WAIT, "confirmed": True})["state"]
    assert s["positions"] == [] and s["realised"] == -1000


def test_gap_down_sells_at_the_open_not_the_stop(store):
    entry_day = daily_rows([(100, 101, 99, 100, 1)])
    robot.check(lambda _: entry_day, plan=lambda d: enter_plan())
    later = daily_rows([(100, 101, 99, 100, 1), (90, 91, 88, 89, 1)])
    s = robot.check(lambda _: later, plan=lambda d: {"verdict": pos.WAIT, "confirmed": True})["state"]
    assert s["realised"] == -2000


def test_ask_mode_waits_for_approval_then_uses_pretend_money(store):
    robot.update_settings({"mode": "ask"})
    df = daily_rows([(100, 101, 99, 100, 1)])
    s = robot.check(lambda _: df, plan=lambda d: enter_plan())["state"]
    assert s["positions"] == [] and len(s["pending"]) == 1
    x = s["pending"][0]
    s = robot.answer(x["id"], True, x["fingerprint"])
    assert s["pending"] == [] and s["positions"][0]["qty"] == 200
    assert "no real order" in s["activity"][0]["why"]


def ask_for_one(store):
    robot.update_settings({"mode": "ask"})
    df = daily_rows([(100, 101, 99, 100, 1)])
    return robot.check(lambda _: df, plan=lambda d: enter_plan())["state"]["pending"][0]


def test_approve_needs_the_exact_suggestion_shown(store):
    x = ask_for_one(store)
    with pytest.raises(ValueError):
        robot.answer(x["id"], True, "something-else")
    with pytest.raises(ValueError):
        robot.answer(x["id"], True)
    assert len(robot.load()["pending"]) == 1          # still open, nothing bought


def test_approve_checks_the_limits_again(store):
    x = ask_for_one(store)
    s = robot.load()
    s["closed"].append({"symbol": "OLD", "bought": "2026-01-01", "date": x["date"], "gain": -2500})
    robot._save(s)
    s = robot.answer(x["id"], True, x["fingerprint"])
    assert s["positions"] == [] and s["activity"][0]["tag"] == "Blocked by your limits"


def test_daily_loss_limit_blocks_new_buys(store):
    s = robot.load()
    s["closed"].append({"symbol": "OLD", "bought": "2026-01-01", "date": "2026-01-05", "gain": -2500})
    robot._save(s)
    df = daily_rows([(100, 101, 99, 100, 1)])         # dated 2026-01-05; 2500 lost + 1000 at risk > 3% of 100000
    s = robot.check(lambda _: df, plan=lambda d: enter_plan())["state"]
    assert s["positions"] == [] and "daily limit" in s["activity"][0]["why"]


def test_trades_per_day_limit(store):
    robot.update_settings({"stocks": ["AAA", "BBB", "CCC"], "max_trades_per_day": 2})
    df = daily_rows([(100, 101, 99, 100, 1)])
    s = robot.check(lambda _: df, plan=lambda d: enter_plan())["state"]
    assert [p["symbol"] for p in s["positions"]] == ["AAA", "BBB"]
    assert "limit for one day" in s["activity"][0]["why"]


def test_open_trades_limit(store):
    robot.update_settings({"max_open": 3})
    s = robot.load()
    s["positions"] = [{"symbol": k, "qty": 1, "entry": 100, "stop": 50, "target": 200, "date": "2025-12-01"} for k in ("X", "Y", "Z")]
    robot._save(s)
    df = daily_rows([(100, 101, 99, 100, 1)])           # never reaches 50 or 200, so all three stay open
    s = robot.check(lambda _: df, plan=lambda d: enter_plan())["state"]
    assert len(s["positions"]) == 3 and "already open" in s["activity"][0]["why"]


def test_limit_settings_only_accept_listed_values(store):
    with pytest.raises(ValueError):
        robot.update_settings({"daily_loss_pct": 50})
    assert robot.update_settings({"daily_loss_pct": 5})["daily_loss_pct"] == 5


def test_stopped_robot_does_nothing(store):
    robot.update_settings({"paused": True})
    def no_data(_):
        raise AssertionError("must not fetch prices")
    assert robot.check(no_data, plan=lambda d: enter_plan())["state"]["positions"] == []


def test_unfinished_candle_is_ignored_before_market_close():
    df = daily_rows([(1, 1, 1, 1, 1), (1, 1, 1, 1, 1)], "2026-10-29")
    assert len(robot.completed(df, datetime(2026, 10, 30, 11, 0, tzinfo=IST))) == 1
    assert len(robot.completed(df, datetime(2026, 10, 30, 15, 31, tzinfo=IST))) == 2


def test_plain_view_has_no_jargon():
    for verdict in (pos.WAIT, pos.AVOID, pos.CHASE):
        text = robot.plain_view({"verdict": verdict, "confirmed": True})
        assert not any(w in text["text"] for w in ("EMA", "RSI", "ATR", "R:R"))
