"""Zerodha Kite Connect: login, historical candles, quotes, holdings, positions.

Needs KITE_API_KEY and KITE_API_SECRET (developers.kite.trade). The daily access
token is created by the dashboard's "Connect Zerodha" button and stored in
state/kite_session.json. Kite does NOT supply fundamentals, delivery % or fund
NAVs - those come from other providers.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from . import normalise

SOURCE = "Zerodha Kite Connect"
SESSION_FILE = Path(__file__).resolve().parents[2] / "state" / "kite_session.json"
_tokens: dict[str, int] = {}


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
    return _client().login_url()


def complete_login(request_token: str) -> dict:
    k = _client()
    data = k.generate_session(request_token, api_secret=os.environ["KITE_API_SECRET"])
    SESSION_FILE.parent.mkdir(exist_ok=True)
    SESSION_FILE.write_text(json.dumps({"access_token": data["access_token"], "user_id": data.get("user_id"),
                                        "date": date.today().isoformat()}))
    return {"user_id": data.get("user_id")}


def connected() -> dict:
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


def ltp(symbols: list[str]) -> dict[str, float]:
    q = _client().ltp([f"NSE:{s}" for s in symbols])
    return {k.split(":", 1)[1]: v["last_price"] for k, v in q.items()}


def holdings() -> list[dict]:
    return _client().holdings()


def positions() -> list[dict]:
    return _client().positions().get("net", [])


def gtts() -> list[dict]:
    return _client().get_gtts()
