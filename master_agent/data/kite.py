"""Zerodha Kite Connect: login, historical candles, quotes, holdings, positions.

Needs KITE_API_KEY and KITE_API_SECRET (developers.kite.trade). The daily access
token is created by the dashboard's "Connect Zerodha" button and stored in
state/kite_session.json. Kite does NOT supply fundamentals, delivery % or fund
NAVs - those come from other providers.
"""
from __future__ import annotations

import json
import math
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from . import kite_mcp, normalise, normalise_hourly

SOURCE = "Zerodha Kite Connect"
SESSION_FILE = Path(__file__).resolve().parents[2] / "state" / "kite_session.json"
_tokens: dict[str, int] = {}


def _provider():
    """Without Kite Connect keys, the same calls go to Zerodha's hosted server."""
    return None if os.environ.get("KITE_API_KEY") else kite_mcp


def _client():
    from kiteconnect import KiteConnect
    key = os.environ.get("KITE_API_KEY")
    if not key:
        raise RuntimeError("KITE_API_KEY is not set (see .env.example)")
    k = KiteConnect(api_key=key)
    if SESSION_FILE.exists():
        s = json.loads(SESSION_FILE.read_text())
        if s.get("date") == date.today().isoformat():
            k.set_access_token(s["access_token"])
    return k


def login_url() -> str:
    if _provider():
        return _provider().login_url()
    return _client().login_url()


def complete_login(request_token: str) -> dict:
    k = _client()
    data = k.generate_session(request_token, api_secret=os.environ["KITE_API_SECRET"])
    SESSION_FILE.parent.mkdir(exist_ok=True)
    SESSION_FILE.write_text(json.dumps({"access_token": data["access_token"], "user_id": data.get("user_id"),
                                        "date": date.today().isoformat()}))
    return {"user_id": data.get("user_id")}


def connected() -> dict:
    if _provider():
        return _provider().connected()
    try:
        p = _client().profile()
        return {"connected": True, "user": p.get("user_name"), "user_id": p.get("user_id")}
    except Exception as e:  # noqa: BLE001 - surface any Kite error to the UI
        return {"connected": False, "reason": str(e)}


def token(symbol: str, exchange: str = "NSE") -> int:
    if not _tokens:
        for i in _client().instruments(exchange):
            _tokens[i["tradingsymbol"]] = i["instrument_token"]
    if symbol not in _tokens:
        raise LookupError(f"{exchange}:{symbol} not found in Kite instruments")
    return _tokens[symbol]


def daily(symbol: str, start: str, end: str | None = None) -> pd.DataFrame:
    if _provider():
        return _provider().daily(symbol, start, end)
    k, tok = _client(), token(symbol)
    s = datetime.fromisoformat(start)
    e = datetime.fromisoformat(end) if end else datetime.now()
    rows = []
    while s <= e:                       # Kite caps day candles at 2000 days per call
        chunk_end = min(s + timedelta(days=1999), e)
        rows += k.historical_data(tok, s, chunk_end, "day")
        s = chunk_end + timedelta(days=1)
    if not rows:
        raise LookupError(f"No Kite candles for {symbol}")
    return normalise(pd.DataFrame(rows))


def hourly(symbol: str) -> pd.DataFrame:
    if _provider():
        return _provider().hourly(symbol)
    e = datetime.now()
    rows = _client().historical_data(token(symbol), e - timedelta(days=380), e, "60minute")
    if not rows:
        raise LookupError(f"No Kite hourly candles for {symbol}")
    return normalise_hourly(pd.DataFrame(rows))


def ltp(symbols: list[str]) -> dict[str, float]:
    q = _client().ltp([f"NSE:{s}" for s in symbols])
    return {k.split(":", 1)[1]: v["last_price"] for k, v in q.items()}


def holdings() -> list[dict]:
    return _provider().holdings() if _provider() else _client().holdings()


def positions() -> list[dict]:
    return _provider().positions() if _provider() else _client().positions().get("net", [])


def gtts() -> list[dict]:
    return _provider().gtts() if _provider() else _client().get_gtts()


# ---- real orders: only with the user's own Kite Connect keys, only from robot.answer() ----

TICK = 0.05
_IST = timezone(timedelta(hours=5, minutes=30))


def orders_ready() -> bool:
    """Own Kite Connect keys and a live login. The key-free hosted connection is never used for orders."""
    return bool(os.environ.get("KITE_API_KEY")) and connected().get("connected", False)


def _orders_client():
    if _provider():
        raise PermissionError("Real orders need your own Kite Connect app keys in .env; the key-free connection is read-only")
    return _client()


def tick(price: float, up: bool = False) -> float:
    """NSE prices move in 5 paise steps."""
    steps = math.ceil(price / TICK - 1e-9) if up else math.floor(price / TICK + 1e-9)
    return round(steps * TICK, 2)


def market_open(now: datetime | None = None) -> bool:
    now = (now or datetime.now(_IST)).astimezone(_IST)
    return now.weekday() < 5 and (9, 15) <= (now.hour, now.minute) < (15, 30)


def place_buy(symbol: str, qty: int, price: float, tag: str, now: datetime | None = None) -> str:
    """A delivery (CNC) LIMIT buy for today only, so it never pays more than the price shown.
    Outside market hours it goes in as an after-market order (AMO) for the next session."""
    k = _orders_client()
    return k.place_order(variety=k.VARIETY_REGULAR if market_open(now) else k.VARIETY_AMO, exchange=k.EXCHANGE_NSE,
                         tradingsymbol=symbol, transaction_type=k.TRANSACTION_TYPE_BUY, quantity=int(qty),
                         product=k.PRODUCT_CNC, order_type=k.ORDER_TYPE_LIMIT, price=tick(price),
                         validity=k.VALIDITY_DAY, tag=tag[:20])


def order_state(order_id: str) -> dict:
    h = _orders_client().order_history(order_id)[-1]
    return {"status": h["status"], "filled": int(h.get("filled_quantity") or 0), "price": float(h.get("average_price") or 0)}


def place_protection(symbol: str, qty: int, last_price: float, stop: float, target: float) -> int:
    """A GTT OCO at Zerodha: one sell at the stop, one at the target; whichever triggers cancels the other.
    The stop leg's limit is 1% under the trigger so it still fills in a falling market."""
    k = _orders_client()
    legs = [{"transaction_type": k.TRANSACTION_TYPE_SELL, "quantity": int(qty), "product": k.PRODUCT_CNC,
             "order_type": k.ORDER_TYPE_LIMIT, "price": tick(stop * 0.99)},
            {"transaction_type": k.TRANSACTION_TYPE_SELL, "quantity": int(qty), "product": k.PRODUCT_CNC,
             "order_type": k.ORDER_TYPE_LIMIT, "price": tick(target, up=True)}]
    res = k.place_gtt(k.GTT_TYPE_OCO, symbol, k.EXCHANGE_NSE, [tick(stop), tick(target, up=True)], float(last_price), legs)
    return res["trigger_id"]


def gtt_status(trigger_id: int) -> str:
    return _orders_client().get_gtt(trigger_id)["status"]
