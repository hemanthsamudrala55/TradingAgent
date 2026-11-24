"""The practice robot behind the simple view: applies positional.plan() to the chosen stocks.

It never talks to a broker. Practice mode trades pretend money by itself; Ask mode waits for
Approve, and approved trades are also pretend money because real orders are not built.
Automatic mode is refused. State lives in state/robot.json (not in Git).
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import pandas as pd

from . import positional as pos

STATE_FILE = Path(__file__).resolve().parents[1] / "state" / "robot.json"
MODES = ("practice", "ask")
RISKS = (0.5, 1, 2)
LIMITS = {"daily_loss_pct": (2, 3, 5), "max_trades_per_day": (1, 2, 3), "max_open": (3, 5, 8)}
IST = timezone(timedelta(hours=5, minutes=30))
MARKET_CLOSE = (15, 30)
_DEFAULT = {"mode": "practice", "money": 100000, "risk_pct": 1, "stocks": [], "paused": False,
            "daily_loss_pct": 3, "max_trades_per_day": 2, "max_open": 5,
            "positions": [], "pending": [], "activity": [], "closed": [], "realised": 0, "seen": {}, "next_id": 1}
_lock = threading.RLock()


def load() -> dict:
    if STATE_FILE.exists():
        return {**json.loads(json.dumps(_DEFAULT)), **json.loads(STATE_FILE.read_text())}
    return json.loads(json.dumps(_DEFAULT))


def _save(s: dict) -> None:
    STATE_FILE.parent.mkdir(exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, indent=1))
    tmp.replace(STATE_FILE)


def _log(s: dict, when: str, tag: str, title: str, why: str) -> None:
    s["activity"].insert(0, {"id": s["next_id"], "when": when, "tag": tag, "title": title, "why": why})
    s["next_id"] += 1
    del s["activity"][200:]


def cash(s: dict) -> float:
    return s["money"] + s["realised"] - sum(p["qty"] * p["entry"] for p in s["positions"])


def update_settings(b: dict) -> dict:
    with _lock:
        s = load()
        if "mode" in b:
            if b["mode"] not in MODES:
                raise ValueError("Automatic mode is locked")
            s["mode"] = b["mode"]
        if "money" in b:
            money = float(b["money"])
            if money <= 0:
                raise ValueError("Enter an amount above zero")
            s["money"] = money
        if "risk_pct" in b:
            if float(b["risk_pct"]) not in RISKS:
                raise ValueError("Choose one of the listed limits")
            s["risk_pct"] = float(b["risk_pct"])
        if "stocks" in b:
            s["stocks"] = sorted({str(x).strip().upper() for x in b["stocks"] if str(x).strip()})
        if "paused" in b:
            s["paused"] = bool(b["paused"])
        for key, allowed in LIMITS.items():
            if key in b:
                if float(b[key]) not in allowed:
                    raise ValueError("Choose one of the listed limits")
                s[key] = float(b[key])
        _save(s)
        return s


def fingerprint(order: dict) -> str:
    """Identifies one exact suggestion, so an Approve can only ever apply to what was shown."""
    keys = ("symbol", "qty", "entry", "stop", "target", "date")
    return hashlib.sha256(json.dumps([order[k] for k in keys]).encode()).hexdigest()[:16]


def risk_check(s: dict, order: dict) -> list[str]:
    """Every buy passes these, in Practice and on Approve. Returns the reasons it is blocked (none = pass)."""
    day, reasons = order["date"], []
    loss = order["qty"] * (order["entry"] - order["stop"])
    cap = s["money"] * s["risk_pct"] / 100
    daily_cap = s["money"] * s["daily_loss_pct"] / 100
    day_result = sum(c["gain"] for c in s["closed"] if c["date"] == day)
    trades_today = sum(1 for p in s["positions"] if p["date"] == day) + sum(1 for c in s["closed"] if c["bought"] == day)
    if order["qty"] < 1 or loss <= 0:
        reasons.append("The trade has no sensible size or exit level.")
    if loss > cap + 0.01:
        reasons.append(f"It could lose ₹{loss:,.0f}, more than your ₹{cap:,.0f} limit for one trade.")
    if -day_result + loss > daily_cap + 0.01:
        reasons.append(f"Losses on {day} could pass your daily limit of ₹{daily_cap:,.0f}.")
    if trades_today >= s["max_trades_per_day"]:
        reasons.append(f"It already made {trades_today} trade(s) on {day}, your limit for one day.")
    if len(s["positions"]) >= s["max_open"]:
        reasons.append(f"{len(s['positions'])} trades are already open, your limit.")
    if any(p["symbol"] == order["symbol"] for p in s["positions"]):
        reasons.append(f"It already holds {order['symbol']}.")
    if order["qty"] * order["entry"] > cash(s) + 0.01:
        reasons.append("There is not enough pretend money left.")
    return reasons


def plain_view(p: dict) -> dict:
    """Turn a positional plan into the words a non-trader sees."""
    v = p["verdict"]
    if not p.get("confirmed"):
        return {"title": "Not enough history", "text": "This stock does not have enough price history for the rules to judge it."}
    if v == pos.ENTER:
        pl = p["plan"]
        return {"title": "Looks ready", "text": f"The buying rules are met near ₹{pl['entry']:,.2f}. The robot would sell if the price closed near ₹{pl['stop']:,.2f}, to limit the loss."}
    if v == pos.CHASE:
        return {"title": "Do not chase", "text": "The price has run up too fast. Buying now risks paying too much."}
    if v == pos.AVOID:
        return {"title": "Stay away for now", "text": "The price is not in a steady upward trend, so the robot stays out."}
    return {"title": "Wait", "text": "The buying rules are not met yet. The robot keeps watching."}


def completed(df: pd.DataFrame, now: datetime | None = None) -> pd.DataFrame:
    """Drop today's candle until the market has closed, so decisions use finished candles only."""
    now = (now or datetime.now(IST)).astimezone(IST)
    if len(df) and df.index[-1].date() == now.date() and (now.hour, now.minute) < MARKET_CLOSE:
        return df.iloc[:-1]
    return df


def _size(s: dict, entry: float, stop: float) -> int:
    per_share = entry - stop
    if per_share <= 0:
        return 0
    return int(min(s["money"] * s["risk_pct"] / 100 / per_share, max(cash(s), 0) / entry))


def _buy(s: dict, sym: str, qty: int, entry: float, stop: float, target: float, when: str, why: str) -> None:
    s["positions"].append({"symbol": sym, "qty": qty, "entry": entry, "stop": stop, "target": target, "date": when})
    _log(s, when, "Pretend trade", f"Bought {qty} {sym} at about ₹{entry:,.2f}", why)


def _manage(s: dict, df: pd.DataFrame, p: dict) -> None:
    """Sell at the first later candle touching the stop or target. If both are touched, assume the stop."""
    for ts, c in df[df.index > pd.Timestamp(p["date"])].iterrows():
        price, why = None, ""
        if c.low <= p["stop"]:
            price, why = min(float(c.open), p["stop"]), "The price fell to the planned exit that limits the loss."
        elif c.high >= p["target"]:
            price, why = max(float(c.open), p["target"]), "The price reached the planned selling level."
        if price is not None:
            gain = (price - p["entry"]) * p["qty"]
            s["realised"] = round(s["realised"] + gain, 2)
            s["positions"].remove(p)
            s["closed"].insert(0, {"symbol": p["symbol"], "bought": p["date"], "date": ts.strftime("%Y-%m-%d"), "gain": round(gain, 2)})
            del s["closed"][500:]
            word = "gain" if gain >= 0 else "loss"
            _log(s, ts.strftime("%Y-%m-%d"), "Pretend trade", f"Sold {p['qty']} {p['symbol']} at about ₹{price:,.2f}, pretend {word} of ₹{abs(gain):,.2f}", why)
            return


def check(get_daily: Callable[[str], pd.DataFrame], now: datetime | None = None, plan=pos.plan) -> dict:
    """One pass over open positions and chosen stocks. Each stock is judged once per finished candle."""
    with _lock:
        s = load()
        errors = []
        if s["paused"]:
            return {"state": s, "errors": errors}
        for p in list(s["positions"]):
            try:
                _manage(s, completed(get_daily(p["symbol"]), now), p)
            except Exception as e:  # noqa: BLE001 - one bad stock must not stop the others
                errors.append({"symbol": p["symbol"], "reason": str(e)})
        for sym in s["stocks"]:
            try:
                df = completed(get_daily(sym), now)
                when = df.index[-1].strftime("%Y-%m-%d")
                if s["seen"].get(sym) == when:
                    continue
                result = plan(df)
            except Exception as e:  # noqa: BLE001
                errors.append({"symbol": sym, "reason": str(e)})
                continue
            s["seen"][sym] = when
            s["pending"] = [x for x in s["pending"] if x["symbol"] != sym]
            view = plain_view(result)
            if any(p["symbol"] == sym for p in s["positions"]):
                continue
            if result["verdict"] != pos.ENTER:
                _log(s, when, "No action", f"Did nothing with {sym}: {view['title']}", view["text"])
                continue
            pl = result["plan"]
            qty = _size(s, pl["entry"], pl["stop"])
            order = {"symbol": sym, "qty": qty, "entry": pl["entry"], "stop": pl["stop"], "target": pl["t1"]["price"], "date": when}
            blocked = risk_check(s, order)
            if qty < 1:
                _log(s, when, "No action", f"Skipped {sym}", "Your money and loss limit are too small to buy even one share.")
            elif blocked:
                _log(s, when, "Blocked by your limits", f"Did not buy {sym}", " ".join(blocked))
            elif s["mode"] == "practice":
                _buy(s, sym, qty, pl["entry"], pl["stop"], pl["t1"]["price"], when, view["text"])
            else:
                s["pending"].append({**order, "id": s["next_id"], "why": view["text"], "fingerprint": fingerprint(order),
                                     "max_loss": round(qty * (pl["entry"] - pl["stop"]), 2)})
                s["next_id"] += 1
        _save(s)
        return {"state": s, "errors": errors}


def answer(pending_id: int, approve: bool, shown: str | None = None) -> dict:
    """An Approve counts only for the exact suggestion the user saw, and only if it still passes the limits."""
    with _lock:
        s = load()
        x = next((y for y in s["pending"] if y["id"] == pending_id), None)
        if not x:
            raise LookupError("This suggestion is no longer open")
        if approve and shown != fingerprint(x):
            raise ValueError("This suggestion changed. Look at it again before approving.")
        s["pending"].remove(x)
        blocked = risk_check(s, x) if approve else []
        if not approve:
            _log(s, x["date"], "Skipped by you", f"Skipped buying {x['qty']} {x['symbol']}", "You chose not to take this trade.")
        elif blocked:
            _log(s, x["date"], "Blocked by your limits", f"Did not buy {x['qty']} {x['symbol']}", " ".join(blocked))
        else:
            _buy(s, x["symbol"], x["qty"], x["entry"], x["stop"], x["target"], x["date"], "You approved this. It is tracked with pretend money, and no real order was sent.")
        _save(s)
        return s
