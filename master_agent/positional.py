"""Positional trading decision framework (Master Instruction 2F and 3I).

Long-only cash-equity setups. Two entry types:
  * pullback - buy inside the immediate support zone, stop below it
  * breakout - buy above the immediate resistance zone once a close clears it
               on expanded volume; the old resistance becomes the stop area

Targets are the next real resistance zones. When there is no resistance in the
data (price discovery) the targets are R-multiples and are labelled projected.
Thresholds come from config/assumptions.yaml.
"""
from __future__ import annotations

import pandas as pd

from . import candles, config, levels as lv, technical as tech

ENTER, WAIT, HOLD, CHASE, AVOID, EXIT = "ENTER", "WAIT", "HOLD", "AVOID CHASING", "AVOID", "EXIT"


def _r(x):
    return None if x is None else round(float(x), 2)


def _targets(entry: float, stop: float, above: list[dict], p: dict) -> tuple[dict, dict]:
    risk = entry - stop
    zs = [z for z in above if z["low"] > entry * 1.002]
    t1 = {"price": _r(zs[0]["low"]), "basis": f"resistance zone {zs[0]['low']:.2f}-{zs[0]['high']:.2f} ({zs[0]['count']} touches)", "projected": False} if zs \
        else {"price": _r(entry + p["projected_t1_r"] * risk), "basis": f"no resistance overhead - projected {p['projected_t1_r']}R", "projected": True}
    t2 = {"price": _r(zs[1]["low"]), "basis": f"resistance zone {zs[1]['low']:.2f}-{zs[1]['high']:.2f} ({zs[1]['count']} touches)", "projected": False} if len(zs) > 1 \
        else {"price": _r(max(entry + p["projected_t2_r"] * risk, (t1["price"] or 0) + risk)), "basis": f"no second resistance - projected {p['projected_t2_r']}R", "projected": True}
    return t1, t2


def evaluate(d: pd.DataFrame, lv_today: dict, lv_prev: dict | None, cfg: dict, position: dict | None = None) -> dict:
    """d: frame from technical.prepare(), cut at 'today'. Returns the trade plan."""
    p, g, v = cfg["positional"], cfg["gaps"], cfg["volume"]
    last, prev = d.iloc[-1], d.iloc[-2]
    c, atr = float(last.close), float(last.atr)
    base = {"as_of": d.index[-1].strftime("%Y-%m-%d"), "close": _r(c), "assumed_timeframe": p["assumed_holding_period"]}

    missing = [k for k in ("ema21", "ema63", "ema200", "rsi", "atr", "vol_avg") if pd.isna(last[k])]
    if missing or not lv_today.get("available"):
        return {**base, "verdict": AVOID, "confirmed": False,
                "reason": "Setup cannot be confirmed - insufficient data: " + (", ".join(missing) or lv_today.get("reason", ""))}

    e21, e63, e200, rsi = float(last.ema21), float(last.ema63), float(last.ema200), float(last.rsi)
    trend_up = c > e200 and e63 > e200
    trend = ("Uptrend" if trend_up and c > e63 else "Pullback in uptrend" if trend_up
             else "Downtrend" if c < e63 < e200 else "No clear uptrend")
    momentum = ("overbought (>70)" if rsi > cfg["rsi"]["overbought"] else "positive (50-70)" if rsi >= 50
                else "weak (30-50)" if rsi >= 30 else "oversold (<30)")
    vol_x = float(last.volume / last.vol_avg) if last.vol_avg else 0
    gap_pct = (last.open / prev.close - 1) * 100
    over = (c / e21 - 1) * 100 > cfg["trend"]["overextended_pct_above_ema21"] or (c - e21) > cfg["trend"]["overextended_atr_above_ema21"] * atr

    # ---- existing position: hold / exit ---------------------------------
    if position:
        stop = position["stop"]
        inv = []
        if c < stop:
            inv.append(f"closed {c:.2f} below stop {stop:.2f}")
        line = position.get("invalidate_below", "ema63")
        if line == "ema63" and c < e63:
            inv.append(f"closed below EMA 63 ({e63:.2f})")
        if line == "ema200" and c < e200:
            inv.append(f"closed below EMA 200 ({e200:.2f})")
        return {**base, "verdict": EXIT if inv else HOLD, "confirmed": True, "trend": trend, "momentum": momentum,
                "stop": _r(stop), "invalidated_by": inv,
                "reason": ("Exit - " + "; ".join(inv)) if inv else f"Hold - trend intact, stop {stop:.2f}"}

    S, R = lv_today.get("immediate_support"), lv_today.get("immediate_resistance")
    above = lv_today.get("resistances", [])

    # ---- breakout today? (close clears yesterday's resistance on volume) --
    breakout = None
    pr = (lv_prev or {}).get("immediate_resistance")
    if pr and prev.close <= pr["high"] < c:
        entry = c
        stop = pr["low"] - p["stop_buffer_atr"] * atr
        t1, t2 = _targets(entry, stop, [z for z in above if z["low"] > pr["high"]], p)
        breakout = {"type": "breakout", "trigger_level": _r(pr["high"]), "entry": _r(entry), "stop": _r(stop),
                    "volume_confirmed": vol_x >= v["breakout_multiple"], "volume_x_avg": round(vol_x, 2), "t1": t1, "t2": t2}

    # ---- pullback plan at the immediate support zone ----------------------
    pull = None
    if S:
        e_low, e_high = S["level"], max(S["high"], S["level"]) + p["entry_zone_above_support_atr"] * atr
        # support "tested" = today's or yesterday's low traded inside the entry zone
        tested = min(float(last.low), float(prev.low)) <= e_high and c >= S["low"]
        entry = c if tested else min(c, e_high)
        stop = S["low"] - p["stop_buffer_atr"] * atr
        t1, t2 = _targets(entry, stop, above, p)
        pull = {"type": "pullback", "entry_zone": [_r(e_low), _r(e_high)], "entry": _r(entry), "stop": _r(stop),
                "support_tested": bool(tested),
                "support_zone": S, "t1": t1, "t2": t2,
                "distance_atr": round((c - e_high) / atr, 2) if atr else None}

    alt = None
    if R and not breakout:
        b_entry = R["high"] * (1 + p["breakout_buffer_pct"] / 100)
        b_stop = R["low"] - p["stop_buffer_atr"] * atr
        t1, t2 = _targets(b_entry, b_stop, [z for z in above if z["low"] > R["high"]], p)
        alt = {"type": "breakout (alternative)", "trigger": f"daily close above {b_entry:.2f} with volume >= {v['breakout_multiple']}x 20-day average",
               "entry": _r(b_entry), "stop": _r(b_stop), "t1": t1, "t2": t2}

    def rr(pl):
        risk = pl["entry"] - pl["stop"]
        return None if risk <= 0 else round((pl["t1"]["price"] - pl["entry"]) / risk, 2)

    for pl in (pull, breakout, alt):
        if pl:
            pl["risk_per_share"] = _r(pl["entry"] - pl["stop"])
            pl["risk_pct"] = _r((pl["entry"] - pl["stop"]) / pl["entry"] * 100)
            pl["rr_t1"] = rr(pl)
            pl["rr_t2"] = None if pl["entry"] <= pl["stop"] else round((pl["t2"]["price"] - pl["entry"]) / (pl["entry"] - pl["stop"]), 2)

    # ---- verdict ----------------------------------------------------------
    reasons, plan, verdict = [], pull or alt, WAIT
    today_patterns = {c["pattern"] for c in candles.detect(d.iloc[-3:], d["ema21"].iloc[-3:], 1)}
    reversal = (last.close > last.open and last.close > prev.high) or bool(
        today_patterns & {"Hammer", "Bullish engulfing", "Morning star"})
    bearish_today = any(dv["type"] == "Bearish divergence" for dv in tech._divergence(d, cfg["rsi"]["divergence_lookback"]))
    if not trend_up:
        verdict = AVOID
        reasons.append(f"EMA structure is not an uptrend (price {c:.2f}, EMA 63 {e63:.2f}, EMA 200 {e200:.2f})")
    elif breakout and breakout["volume_confirmed"] and breakout["rr_t1"] and breakout["rr_t1"] >= p["min_risk_reward"] \
            and breakout["risk_pct"] <= p["max_stop_pct"] and gap_pct < g["chase_gap_pct"]:
        verdict, plan = ENTER, breakout
        reasons.append(f"Closed above resistance {breakout['trigger_level']:.2f} on {vol_x:.1f}x average volume")
    elif breakout and gap_pct >= g["chase_gap_pct"]:
        verdict, plan = CHASE, breakout
        reasons.append(f"Breakout came with a {gap_pct:.1f}% gap-up; stop distance {breakout['risk_pct']:.1f}% - wait for a retest of {breakout['trigger_level']:.2f}")
    elif breakout and not breakout["volume_confirmed"]:
        plan = breakout
        reasons.append(f"Close above {breakout['trigger_level']:.2f} but volume only {vol_x:.1f}x average - breakout not confirmed")
    elif over or (gap_pct >= g["chase_gap_pct"] and pull and c > pull["entry_zone"][1]):
        verdict = CHASE
        reasons.append(f"Overextended: {((c / e21 - 1) * 100):.1f}% above EMA 21" if over else f"Gap-up of {gap_pct:.1f}% away from support")
    elif pull and (pull["support_tested"] or pull["entry_zone"][0] <= c <= pull["entry_zone"][1]):
        ok_rr = pull["rr_t1"] is not None and pull["rr_t1"] >= p["min_risk_reward"]
        ok_stop = pull["risk_pct"] <= p["max_stop_pct"]
        ok_mom = (rsi > float(prev.rsi)) and not bearish_today and (reversal or not p["pullback_needs_reversal_candle"])
        if ok_rr and ok_stop and ok_mom:
            verdict = ENTER
            reasons.append(f"Support zone {pull['support_zone']['low']:.2f}-{pull['support_zone']['high']:.2f} tested and held "
                           f"(reversal candle, RSI turning up); R:R {pull['rr_t1']} to T1")
        else:
            if not ok_rr:
                reasons.append(f"R:R to T1 is {pull['rr_t1']} - below the {p['min_risk_reward']} minimum")
            if not ok_stop:
                reasons.append(f"Stop needs {pull['risk_pct']}% - wider than {p['max_stop_pct']}%")
            if not ok_mom:
                reasons.append("Support not yet confirmed - waiting for a bullish reversal candle with RSI turning up")
    elif pull:
        reasons.append(f"Price {c:.2f} is {pull['distance_atr']} ATR above the entry zone {pull['entry_zone'][0]:.2f}-{pull['entry_zone'][1]:.2f}")
    else:
        reasons.append("No support zone below price in the last year of data")

    invalid = []
    if plan:
        invalid.append(f"Daily close below stop {plan['stop']:.2f}")
    inv_line = "ema63" if c > e63 else "ema200"
    invalid.append(f"Daily close below EMA 63 ({e63:.2f})" if inv_line == "ema63" else f"Daily close below EMA 200 ({e200:.2f})")
    invalid.append("Bearish RSI divergence with RSI falling below 50")

    risks = [f"Gap-down risk: an overnight gap can open below the stop; the loss can exceed the planned {plan['risk_pct']}%" if plan else "Gap-down risk"]
    if rsi > cfg["rsi"]["overbought"]:
        risks.append("RSI above 70 - pullbacks are more likely; size smaller")
    if bearish_today:
        risks.append("Bearish RSI divergence present")

    return {**base, "verdict": verdict, "confirmed": True, "trend": trend, "momentum": momentum,
            "rsi": round(rsi, 1), "volume_x_avg": round(vol_x, 2), "gap_today_pct": round(gap_pct, 2),
            "overextended": bool(over), "plan": plan, "pullback_plan": pull, "breakout_plan": breakout or alt,
            "reasons": reasons, "invalidation": invalid, "invalidate_below": inv_line, "risks": risks}


def plan(df: pd.DataFrame, cfg: dict | None = None, position: dict | None = None) -> dict:
    cfg = cfg or config.load()
    d = tech.prepare(df, cfg)
    return evaluate(d, lv.find_levels(df, cfg), lv.find_levels(df.iloc[:-1], cfg) if len(df) > 40 else None, cfg, position)
