from datetime import datetime, timedelta, timezone

import pandas as pd

from master_agent import config, picks, positional as pos

IST = timezone(timedelta(hours=5, minutes=30))
CFG = config.load()


def df(days=30, last="2026-11-20"):
    idx = pd.bdate_range(end=last, periods=days)
    return pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1e6}, index=idx)


def zone_plan(**pull):
    base = {"entry_zone": [95.0, 98.0], "support_tested": False, "rr_t1": 2.5, "risk_pct": 3.0, "distance_atr": 2.0}
    return {"verdict": pos.WAIT, "confirmed": True, "close": 100.0, "as_of": "2026-11-20",
            "pullback_plan": {**base, **pull}, "breakout_plan": None, "plan": None}


def test_ready_stock_comes_first_with_its_prices():
    enter = {"verdict": pos.ENTER, "confirmed": True, "close": 100.0, "as_of": "2026-11-20",
             "plan": {"entry": 100.0, "stop": 95.0, "t1": {"price": 110.0}}}
    plans = {"AAA": {"verdict": pos.AVOID, "confirmed": True}, "BBB": enter}
    rows = [picks.judge("AAA", df(), CFG, lambda d, c: plans["AAA"]), picks.judge("BBB", df(), CFG, lambda d, c: plans["BBB"])]
    rows.sort(key=lambda r: r["score"])
    assert rows[0]["symbol"] == "BBB" and rows[0]["group"] == "ready"
    assert (rows[0]["entry"], rows[0]["stop"], rows[0]["target"]) == (100.0, 95.0, 110.0)
    assert rows[1]["group"] == "later"


def test_wait_near_floor_is_getting_close():
    r = picks.judge("X", df(), CFG, lambda d, c: zone_plan(support_tested=True))
    assert r["group"] == "close" and "floor" in r["text"]


def test_wait_far_above_zone_is_later_and_says_how_far():
    r = picks.judge("X", df(), CFG, lambda d, c: zone_plan(distance_atr=3.0))
    assert r["group"] == "later" and "2.0% above its buying zone" in r["text"]


def test_wait_at_floor_with_poor_reward_explains_why():
    r = picks.judge("X", df(), CFG, lambda d, c: zone_plan(support_tested=True, rr_t1=0.5))
    assert "gain is small" in r["text"] and r["group"] == "later"


def test_scan_skips_bad_symbols_and_sorts():
    plans = {"GOOD": zone_plan(support_tested=True), "FAR": zone_plan(distance_atr=4.0)}

    def get(sym):
        if sym == "BAD":
            raise LookupError("no prices")
        d = df()
        d.attrs["sym"] = sym
        return d
    res = picks.scan(["FAR", "BAD", "GOOD"], get, plan=lambda d, c: plans[d.attrs["sym"]])
    assert [r["symbol"] for r in res["rows"]] == ["GOOD", "FAR"]
    assert res["skipped"] == [{"symbol": "BAD", "error": "no prices"}] and res["scanned"] == 3


def test_scan_ignores_todays_unfinished_candle():
    seen = []
    plan = lambda d, c: seen.append(d.index[-1]) or zone_plan()   # noqa: E731
    today = df(last="2026-11-25")
    picks.scan(["X"], lambda s: today, now=datetime(2026, 11, 25, 11, 0, tzinfo=IST), plan=plan)
    assert seen == [pd.Timestamp("2026-11-24")]


def test_picks_endpoint_is_public(monkeypatch):
    from werkzeug.security import generate_password_hash
    from web import app as webapp
    monkeypatch.setenv("OWNER_PASSWORD_HASH", generate_password_hash("x" * 12))
    monkeypatch.setitem(webapp._picks, "result", {"rows": [], "skipped": [], "scanned": 0, "as_of": None})
    monkeypatch.setitem(webapp._picks, "at", 1e18)
    r = webapp.app.test_client().get("/api/picks")
    assert r.status_code == 200 and r.get_json()["rows"] == []


def test_picks_carry_the_robots_levels_for_budget_sizing():
    r = picks.judge("X", df(), CFG, lambda d, c: {**zone_plan(support_tested=True),
                                                 "plan": {"entry": 98.0, "stop": 94.0, "t1": {"price": 108.0}}})
    assert (r["entry"], r["stop"], r["target"]) == (98.0, 94.0, 108.0)
    assert "entry" not in picks.judge("X", df(), CFG, lambda d, c: {"verdict": pos.AVOID, "confirmed": True})


def test_prices_endpoint_is_owner_only_and_uses_yahoo(monkeypatch, tmp_path):
    from werkzeug.security import generate_password_hash
    from master_agent import robot
    from master_agent.data import yahoo
    from web import app as webapp
    monkeypatch.setattr(robot, "STATE_FILE", tmp_path / "robot.json")
    s = robot.load()
    s["positions"] = [{"symbol": "AAA", "qty": 10, "entry": 100.0, "stop": 95.0, "target": 110.0, "date": "2026-11-20"}]
    s["stocks"] = ["BBB"]
    robot._save(s)
    monkeypatch.setattr(yahoo, "ltp", lambda syms: {x: {"price": 103.5, "time": "2026-11-25T10:00:00+05:30"} for x in syms})
    monkeypatch.setitem(webapp._quotes, "at", 0.0)
    monkeypatch.delenv("KITE_API_KEY", raising=False)
    monkeypatch.delenv("OWNER_PASSWORD_HASH", raising=False)
    r = webapp.app.test_client().get("/api/robot/prices").get_json()
    assert r["prices"]["AAA"]["price"] == 103.5 and "BBB" in r["prices"]
    monkeypatch.setenv("OWNER_PASSWORD_HASH", generate_password_hash("x" * 12))
    assert webapp.app.test_client().get("/api/robot/prices").status_code == 401


def test_closed_trade_keeps_shares_and_prices():
    from master_agent import robot
    p = {"symbol": "AAA", "qty": 10, "entry": 100.0, "stop": 95.0, "target": 110.0, "date": "2026-11-20"}
    s = {"positions": [p], "closed": []}
    robot._close(s, p, "2026-11-24", 100.0)
    c = s["closed"][0]
    assert (c["qty"], c["entry"], c["exit"], c["gain"]) == (10, 100.0, 110.0, 100.0)


def test_picks_rescan_when_a_chosen_stock_was_not_judged(monkeypatch, tmp_path):
    from master_agent import robot
    from web import app as webapp
    monkeypatch.setattr(robot, "STATE_FILE", tmp_path / "robot.json")
    robot.update_settings({"stocks": ["NEWONE"]})
    monkeypatch.delenv("OWNER_PASSWORD_HASH", raising=False)
    monkeypatch.setitem(webapp._picks, "result", {"rows": [], "skipped": [], "scanned": 0, "as_of": None})
    monkeypatch.setitem(webapp._picks, "at", 1e18)
    monkeypatch.setitem(webapp._picks, "busy", False)
    started = []
    monkeypatch.setattr(webapp.threading, "Thread", lambda target, daemon: type("T", (), {"start": lambda self: started.append(1)})())
    assert webapp.app.test_client().get("/api/picks").get_json()["working"] is True
    assert started == [1] and "NEWONE" in webapp._picks_symbols()
    webapp._picks["busy"] = False
