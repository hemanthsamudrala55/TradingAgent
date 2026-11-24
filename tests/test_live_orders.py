"""Real-order paths, against a fake Zerodha. No test here reaches the network."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from kiteconnect import KiteConnect

from master_agent import positional as pos, robot
from master_agent.data import kite

IST = timezone(timedelta(hours=5, minutes=30))


class FakeBroker:
    def __init__(self, fill=("COMPLETE", 10, 99.5), gtt="active", fail_buy=None, fail_gtt=None):
        self.fill, self.gtt, self.fail_buy, self.fail_gtt = fill, gtt, fail_buy, fail_gtt
        self.buys, self.protections = [], []

    def place_buy(self, symbol, qty, price, tag):
        if self.fail_buy:
            raise RuntimeError(self.fail_buy)
        self.buys.append((symbol, qty, price, tag))
        return "ORDER1"

    def order_state(self, order_id):
        status, filled, price = self.fill
        return {"status": status, "filled": filled, "price": price}

    def place_protection(self, symbol, qty, last_price, stop, target):
        if self.fail_gtt:
            raise RuntimeError(self.fail_gtt)
        self.protections.append((symbol, qty, stop, target))
        return 77

    def gtt_status(self, trigger_id):
        return self.gtt


@pytest.fixture
def live(monkeypatch, tmp_path):
    monkeypatch.setattr(robot, "STATE_FILE", tmp_path / "robot.json")
    robot.update_settings({"stocks": ["INFY"], "mode": "ask"})
    robot.update_settings({"live": True, "confirm": "real money"}, broker_ready=True)
    df = pd.DataFrame({"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.0], "volume": [1.0]},
                      index=pd.bdate_range("2026-01-05", periods=1))
    plan = lambda d: {"verdict": pos.ENTER, "confirmed": True, "plan": {"entry": 100.0, "stop": 95.0, "t1": {"price": 110.0}}}
    s = robot.check(lambda _: df, plan=plan)["state"]
    return s["pending"][0]


def test_switching_on_needs_phrase_ask_mode_and_broker(monkeypatch, tmp_path):
    monkeypatch.setattr(robot, "STATE_FILE", tmp_path / "robot.json")
    with pytest.raises(ValueError, match="Ask me first"):
        robot.update_settings({"live": True, "confirm": "REAL MONEY"}, broker_ready=True)
    robot.update_settings({"mode": "ask"})
    with pytest.raises(ValueError, match="Kite Connect"):
        robot.update_settings({"live": True, "confirm": "REAL MONEY"}, broker_ready=False)
    with pytest.raises(ValueError, match="Type REAL MONEY"):
        robot.update_settings({"live": True, "confirm": "yes"}, broker_ready=True)
    assert robot.update_settings({"live": True, "confirm": "REAL MONEY"}, broker_ready=True)["live"] is True
    assert robot.update_settings({"mode": "practice"})["live"] is False


def test_check_never_places_an_order(live):
    b = FakeBroker()
    robot.check(lambda _: (_ for _ in ()).throw(LookupError("x")), broker=b)
    assert b.buys == []


def test_real_order_needs_the_typed_confirmation(live):
    b = FakeBroker()
    for wrong in (None, "yes", "BUY 10 INFY", "BUY 200 TCS"):
        with pytest.raises(ValueError, match="BUY 200 INFY"):
            robot.answer(live["id"], True, live["fingerprint"], wrong, b)
    assert b.buys == [] and len(robot.load()["pending"]) == 1


def test_confirmed_order_is_sent_once_as_a_limit(live):
    b = FakeBroker()
    s = robot.answer(live["id"], True, live["fingerprint"], " buy 200  infy ", b)
    assert b.buys == [("INFY", 200, 100.0, "robot" + live["fingerprint"][:15])]
    p = s["positions"][0]
    assert p["live"] and p["status"] == "ordered" and p["order_id"] == "ORDER1"
    with pytest.raises(LookupError):                   # the suggestion is used up: no second order
        robot.answer(live["id"], True, live["fingerprint"], "BUY 200 INFY", b)
    assert len(b.buys) == 1


def test_refused_order_is_logged_and_not_retried(live):
    b = FakeBroker(fail_buy="IP not allowed")
    s = robot.answer(live["id"], True, live["fingerprint"], "BUY 200 INFY", b)
    assert s["positions"] == [] and s["pending"] == []
    assert "IP not allowed" in s["activity"][0]["why"] and "not be retried" in s["activity"][0]["why"]


def test_no_order_when_stopped_or_broker_missing(live):
    with pytest.raises(ValueError, match="not connected"):
        robot.answer(live["id"], True, live["fingerprint"], "BUY 200 INFY", None)
    robot.update_settings({"paused": True})
    with pytest.raises(ValueError, match="stopped"):
        robot.answer(live["id"], True, live["fingerprint"], "BUY 200 INFY", FakeBroker())


def test_fill_then_stop_loss_then_close(live):
    b = FakeBroker(fill=("COMPLETE", 150, 99.5))
    robot.answer(live["id"], True, live["fingerprint"], "BUY 200 INFY", b)
    s = robot.check(lambda _: (_ for _ in ()).throw(LookupError("x")), broker=b)["state"]
    p = s["positions"][0]
    assert (p["qty"], p["entry"], p["status"], p["gtt_id"]) == (150, 99.5, "protected", 77)
    assert b.protections == [("INFY", 150, 95.0, 110.0)]
    b.gtt = "triggered"
    s = robot.check(lambda _: (_ for _ in ()).throw(LookupError("x")), broker=b)["state"]
    assert s["positions"] == [] and s["closed"][0]["gain"] is None and s["closed"][0]["live"]


def test_missing_stop_loss_is_flagged_and_retried(live):
    b = FakeBroker(fail_gtt="GTT rejected")
    robot.answer(live["id"], True, live["fingerprint"], "BUY 200 INFY", b)
    s = robot.check(lambda _: (_ for _ in ()).throw(LookupError("x")), broker=b)["state"]
    assert s["positions"][0]["status"] == "unprotected" and s["activity"][0]["tag"] == "Needs you now"
    b.fail_gtt = None
    s = robot.check(lambda _: (_ for _ in ()).throw(LookupError("x")), broker=b)["state"]
    assert s["positions"][0]["status"] == "protected"


def test_unfilled_order_is_removed(live):
    b = FakeBroker(fill=("CANCELLED", 0, 0))
    robot.answer(live["id"], True, live["fingerprint"], "BUY 200 INFY", b)
    s = robot.check(lambda _: (_ for _ in ()).throw(LookupError("x")), broker=b)["state"]
    assert s["positions"] == [] and b.protections == []


def test_unknown_real_close_counts_as_full_loss_for_limits(live):
    s = robot.load()
    s["closed"].append({"symbol": "OLD", "bought": "2026-01-05", "date": "2026-01-05", "gain": None, "max_loss": 2500, "live": True})
    order = {"symbol": "TCS", "qty": 200, "entry": 100.0, "stop": 95.0, "target": 110.0, "date": "2026-01-05"}
    assert any("daily limit" in r for r in robot.risk_check(s, order))


# ---- the Kite order calls themselves, with Zerodha's client replaced ----

class FakeKite(KiteConnect):
    def __init__(self):
        super().__init__(api_key="test")
        self.calls = []

    def place_order(self, **kw):
        self.calls.append(("order", kw))
        return "ORDER1"

    def place_gtt(self, *a):
        self.calls.append(("gtt", a))
        return {"trigger_id": 5}


def test_buy_is_a_cnc_limit_and_uses_amo_out_of_hours(monkeypatch):
    fake = FakeKite()
    monkeypatch.setenv("KITE_API_KEY", "test")
    monkeypatch.setattr(kite, "_client", lambda: fake)
    kite.place_buy("INFY", 10, 1185.03, "robotabc", now=datetime(2026, 11, 24, 10, 0, tzinfo=IST))
    kite.place_buy("INFY", 10, 1185.03, "robotabc", now=datetime(2026, 11, 24, 20, 0, tzinfo=IST))
    day, night = fake.calls[0][1], fake.calls[1][1]
    assert (day["variety"], night["variety"]) == ("regular", "amo")
    assert (day["product"], day["order_type"], day["price"], day["validity"]) == ("CNC", "LIMIT", 1185.0, "DAY")


def test_protection_is_one_oco_with_both_legs(monkeypatch):
    fake = FakeKite()
    monkeypatch.setenv("KITE_API_KEY", "test")
    monkeypatch.setattr(kite, "_client", lambda: fake)
    assert kite.place_protection("INFY", 10, 1185, 1150.02, 1260.01) == 5
    trigger_type, sym, exch, triggers, last, legs = fake.calls[0][1]
    assert trigger_type == "two-leg" and triggers == [1150.0, 1260.05]
    assert [l["transaction_type"] for l in legs] == ["SELL", "SELL"] and legs[0]["price"] < 1150


def test_orders_refused_without_own_keys(monkeypatch):
    monkeypatch.delenv("KITE_API_KEY", raising=False)
    with pytest.raises(PermissionError):
        kite.place_buy("INFY", 1, 100, "t")
    assert kite.orders_ready() is False


def test_price_ticks():
    assert (kite.tick(100.03), kite.tick(100.03, up=True), kite.tick(100.05)) == (100.0, 100.05, 100.05)
