"""Zerodha's hosted Kite MCP server (mcp.kite.trade): market data without Kite Connect keys.

Used when KITE_API_KEY is not set. The login is the user's own, on Zerodha's page. The
server also offers order tools, so every call goes through READ_ONLY_TOOLS and anything
else is refused here. The session id is a credential: it lives in state/ (not in Git).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

from . import normalise, normalise_hourly

URL = "https://mcp.kite.trade/mcp"
SESSION_FILE = Path(__file__).resolve().parents[2] / "state" / "kite_mcp_session.json"
READ_ONLY_TOOLS = frozenset({"login", "get_profile", "search_instruments", "get_historical_data",
                             "get_holdings", "get_positions", "get_gtts"})
_LOGIN_LINK = re.compile(r"https://mcp\.kite\.trade/authorize\?session_id=[\w\-.~%]+")
_tokens: dict[str, int] = {}


def _load_session() -> str | None:
    if SESSION_FILE.exists():
        return json.loads(SESSION_FILE.read_text()).get("session_id")
    return None


def _post(body: dict, session: str | None) -> requests.Response:
    headers = {"Accept": "application/json, text/event-stream"}
    if session:
        headers["Mcp-Session-Id"] = session
    r = requests.post(URL, json=body, headers=headers, timeout=30)
    r.raise_for_status()
    return r


def _parse(r: requests.Response) -> dict:
    """The server answers with plain JSON or a server-sent event."""
    if "text/event-stream" in r.headers.get("Content-Type", ""):
        for line in r.text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:])
        raise ValueError("Empty reply from Kite MCP")
    return r.json()


def _new_session() -> str:
    r = _post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
               "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                          "clientInfo": {"name": "trading-agent-dashboard", "version": "1.0"}}}, None)
    session = r.headers["Mcp-Session-Id"]
    _post({"jsonrpc": "2.0", "method": "notifications/initialized"}, session)
    SESSION_FILE.parent.mkdir(exist_ok=True)
    SESSION_FILE.write_text(json.dumps({"session_id": session}))
    return session


def call(tool: str, session: str | None = None, **args):
    """Call one allow-listed tool. Returns its decoded result, or raises with the server's message."""
    if tool not in READ_ONLY_TOOLS:
        raise PermissionError(f"{tool} is not allowed: this dashboard is read-only")
    session = session or _load_session() or _new_session()
    res = _parse(_post({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                        "params": {"name": tool, "arguments": args}}, session))
    if "error" in res:
        raise RuntimeError(res["error"].get("message", "Kite MCP error"))
    text = "".join(c.get("text", "") for c in res["result"].get("content", []))
    if res["result"].get("isError"):
        raise RuntimeError(text)
    try:
        return json.loads(text)
    except ValueError:
        return text


def login_url() -> str:
    """Always a fresh session, so an expired one can never be reused."""
    text = call("login", session=_new_session())
    m = _LOGIN_LINK.search(text if isinstance(text, str) else "")
    if not m:
        raise RuntimeError("Kite MCP did not return a Zerodha login link")
    return m.group(0)


def connected() -> dict:
    """No saved session means the user never logged in here, so skip the network call."""
    if not _load_session():
        return {"connected": False, "reason": "Not logged in"}
    try:
        p = call("get_profile")
        return {"connected": True, "user": p.get("user_name"), "user_id": p.get("user_id")}
    except Exception as e:  # noqa: BLE001 - surface any Kite error to the UI
        return {"connected": False, "reason": str(e)}


def _rows(res) -> list[dict]:
    """Paginated tools wrap their list in {"data": [...]}."""
    return res.get("data") or [] if isinstance(res, dict) else res or []


def token(symbol: str, exchange: str = "NSE") -> int:
    if symbol not in _tokens:
        for i in _rows(call("search_instruments", query=f"{exchange}:{symbol}", filter_on="id")):
            if i.get("tradingsymbol") == symbol and i.get("exchange") == exchange:
                _tokens[symbol] = i["instrument_token"]
                break
    if symbol not in _tokens:
        raise LookupError(f"{exchange}:{symbol} not found in Kite instruments")
    return _tokens[symbol]


def daily(symbol: str, start: str, end: str | None = None) -> pd.DataFrame:
    tok = token(symbol)
    s = datetime.fromisoformat(start)
    e = datetime.fromisoformat(end) if end else datetime.now()
    rows = []
    while s <= e:                       # Kite caps day candles at 2000 days per call
        chunk_end = min(s + timedelta(days=1999), e)
        rows += _rows(call("get_historical_data", instrument_token=tok, interval="day",
                           from_date=s.strftime("%Y-%m-%d %H:%M:%S"), to_date=chunk_end.strftime("%Y-%m-%d %H:%M:%S")))
        s = chunk_end + timedelta(days=1)
    if not rows:
        raise LookupError(f"No Kite candles for {symbol}")
    return normalise(pd.DataFrame(rows))


def hourly(symbol: str) -> pd.DataFrame:
    e = datetime.now()
    rows = _rows(call("get_historical_data", instrument_token=token(symbol), interval="60minute",
                      from_date=(e - timedelta(days=380)).strftime("%Y-%m-%d %H:%M:%S"), to_date=e.strftime("%Y-%m-%d %H:%M:%S")))
    if not rows:
        raise LookupError(f"No Kite hourly candles for {symbol}")
    return normalise_hourly(pd.DataFrame(rows))


def holdings() -> list[dict]:
    return _rows(call("get_holdings"))


def positions() -> list[dict]:
    return call("get_positions").get("net", [])


def gtts() -> list[dict]:
    return _rows(call("get_gtts"))
