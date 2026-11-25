"""Robot's picks: run the robot's buying rules over a list of stocks and say, in plain words,
which ones are ready now and which are getting close. Read-only: it never buys anything.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Callable

import pandas as pd

from . import config, positional as pos, robot

CLOSE_ATR = 1.0      # a stock within 1 ATR of its buying zone counts as "getting close"


def _money(x: float) -> str:
    return f"₹{x:,.2f}"


def judge(sym: str, df: pd.DataFrame, cfg: dict, plan=pos.plan) -> dict:
    """One stock -> {symbol, group, title, text, close, score, ...}. Lower score = nearer a buy."""
    p = plan(df, cfg)
    row = {"symbol": sym, "close": p.get("close"), "as_of": p.get("as_of")}
    v, pp = p["verdict"], cfg["positional"]
    if not p.get("confirmed"):
        return {**row, "group": "later", "score": 99, "title": "Not enough history", "text": "Too little price history to judge."}
    if v == pos.ENTER:
        pl = p["plan"]
        return {**row, **_levels(pl), "group": "ready", "score": -1, "title": "Ready now",
                "text": f"Buying rules met near {_money(pl['entry'])}. It would sell near {_money(pl['t1']['price'])} for a gain, "
                        f"or near {_money(pl['stop'])} to limit the loss."}
    if v == pos.CHASE:
        return {**row, "group": "later", "score": 50, "title": "Do not chase", "text": "Rose too fast. Buying now risks paying too much."}
    if v == pos.AVOID:
        return {**row, "group": "later", "score": 60, "title": "Stay away", "text": "Not in a steady upward trend."}

    # WAIT: work out how near it is, and why it is not a buy yet
    pull, brk = p.get("pullback_plan"), p.get("breakout_plan")
    c = p["close"]
    if brk and brk.get("type") == "breakout" and not brk.get("volume_confirmed"):
        score, text = 0.3, f"Just rose above its ceiling ({_money(brk['trigger_level'])}), but on low volume. Waiting for proof."
    elif pull and (pull["support_tested"] or pull["entry_zone"][0] <= c <= pull["entry_zone"][1]):
        if pull["rr_t1"] is None or pull["rr_t1"] < pp["min_risk_reward"]:
            score, text = 1.5, "At its floor, but the possible gain is small for the risk. Waiting for a better setup."
        elif pull["risk_pct"] > pp["max_stop_pct"]:
            score, text = 1.5, "At its floor, but the safety stop would be too far below. Waiting."
        else:
            score, text = 0.1, f"At its floor near {_money(pull['entry_zone'][0])}. Waiting for a sign the price will bounce."
    elif pull and pull.get("distance_atr") is not None:
        score = max(float(pull["distance_atr"]), 0.2)
        gap = (c - pull["entry_zone"][1]) / c * 100
        text = (f"Upward trend. About {gap:.1f}% above its buying zone "
                f"({_money(pull['entry_zone'][0])} to {_money(pull['entry_zone'][1])}). Waiting for a dip.")
    else:
        score, text = 20, "Upward trend, but no clear floor to buy at yet."
    pl = brk if score == 0.3 else p.get("plan")
    return {**row, **_levels(pl), "group": "close" if score <= CLOSE_ATR else "later", "score": round(score, 2),
            "title": "Getting close" if score <= CLOSE_ATR else "Wait", "text": text}


def _levels(pl: dict | None) -> dict:
    """The buy, stop and target the robot would use, so the page can size it to your budget."""
    if not pl or pl.get("entry") is None or pl.get("stop") is None or pl["entry"] <= pl["stop"]:
        return {}
    return {"entry": pl["entry"], "stop": pl["stop"], "target": (pl.get("t1") or {}).get("price")}


def scan(symbols: list[str], get_daily: Callable[[str], pd.DataFrame], now: datetime | None = None,
         plan=pos.plan, workers: int = 6) -> dict:
    """Judge every symbol on finished daily candles. Returns rows sorted nearest-to-a-buy first."""
    cfg = config.load()

    def one(sym):
        try:
            return judge(sym, robot.completed(get_daily(sym), now), cfg, plan)
        except Exception as e:  # noqa: BLE001 - one bad symbol must not stop the scan
            return {"symbol": sym, "error": str(e) or type(e).__name__}

    with ThreadPoolExecutor(workers) as ex:
        results = list(ex.map(one, symbols))
    rows = sorted((r for r in results if "error" not in r), key=lambda r: (r["score"], r["symbol"]))
    return {"rows": rows, "skipped": [r for r in results if "error" in r], "scanned": len(symbols),
            "as_of": max((r["as_of"] for r in rows if r.get("as_of")), default=None)}
