"""Technical analysis framework (Master Instruction section 3, A-H)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import candles, config, indicators as ind, levels as lv


def _r(x, n=2):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), n)


def _slope(s: pd.Series, n: int, flat_pct: float) -> str:
    if len(s.dropna()) <= n:
        return "unavailable"
    chg = (s.iloc[-1] / s.iloc[-1 - n] - 1) * 100
    return "flattening" if abs(chg) < flat_pct else "rising" if chg > 0 else "falling"


def prepare(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    i = cfg["indicators"]
    out = df.copy()
    out["ema21"] = ind.ema(out["close"], i["ema_fast"])
    out["ema63"] = ind.ema(out["close"], i["ema_mid"])
    out["ema200"] = ind.ema(out["close"], i["ema_slow"])
    out["rsi"] = ind.rsi(out["close"], i["rsi_period"])
    out["atr"] = ind.atr(out, i["atr_period"])
    out["vol_avg"] = out["volume"].rolling(i["volume_avg_days"]).mean()
    return out


def ema_analysis(d: pd.DataFrame, cfg: dict) -> dict:
    t = cfg["trend"]
    last = d.iloc[-1]
    c = last.close
    e = {k: last[k] for k in ("ema21", "ema63", "ema200")}
    if any(pd.isna(v) for v in e.values()):
        avail = [k for k, v in e.items() if not pd.isna(v)]
        return {"available": False, "reason": f"Not enough history for all EMAs (have {len(d)} candles; EMA 200 needs 200).",
                "values": {k: _r(v) for k, v in e.items()}, "computed": avail}
    slopes = {k: _slope(d[k], t["slope_lookback"], t["flat_slope_pct"]) for k in e}
    dist = {k: _r((c / v - 1) * 100) for k, v in e.items()}

    events = []
    tail = d.iloc[-60:]
    for a, b, name in (("ema21", "ema63", "EMA 21 / EMA 63"), ("ema63", "ema200", "EMA 63 / EMA 200")):
        diff = np.sign(tail[a] - tail[b])
        x = diff.diff().fillna(0)
        for dt in tail.index[x > 0]:
            events.append({"date": dt.strftime("%Y-%m-%d"), "event": f"Bullish crossover {name}"})
        for dt in tail.index[x < 0]:
            events.append({"date": dt.strftime("%Y-%m-%d"), "event": f"Bearish crossover {name}"})
    rec = d.iloc[-10:]
    for k, lbl in (("ema21", "EMA 21"), ("ema63", "EMA 63"), ("ema200", "EMA 200")):
        for j in range(1, len(rec)):
            r, p = rec.iloc[j], rec.iloc[j - 1]
            if p.close < p[k] and r.close > r[k]:
                events.append({"date": rec.index[j].strftime("%Y-%m-%d"), "event": f"Price reclaimed {lbl}"})
            if r.high >= r[k] and r.close < r[k] and p.close < p[k]:
                events.append({"date": rec.index[j].strftime("%Y-%m-%d"), "event": f"Price rejected at {lbl} (resistance)"})
    events.sort(key=lambda x: x["date"])

    over = (dist["ema21"] > t["overextended_pct_above_ema21"]
            or (c - e["ema21"]) > t["overextended_atr_above_ema21"] * last.atr)

    e21, e63, e200 = e["ema21"], e["ema63"], e["ema200"]
    if c > e21 > e63 > e200 and slopes["ema63"] == "rising" and slopes["ema200"] == "rising":
        structure = "Strong uptrend - price above rising EMA 21 > 63 > 200"
    elif e63 > e200 and c > e63:
        structure = "Uptrend - EMA 63 above EMA 200, price above EMA 63"
    elif e63 > e200 and c > e200:
        structure = "Pullback inside a longer uptrend - price below EMA 21/63 but above EMA 200"
    elif c < e21 < e63 < e200:
        structure = "Downtrend - price below falling EMA stack 21 < 63 < 200"
    elif c < e200:
        structure = "Weak - price below EMA 200"
    else:
        structure = "Mixed / sideways - EMAs not aligned"

    return {
        "available": True,
        "values": {k: _r(v) for k, v in e.items()},
        "price_vs": {k: "above" if c > v else "below" for k, v in e.items()},
        "ema21_vs_ema63": "above" if e21 > e63 else "below",
        "ema63_vs_ema200": "above" if e63 > e200 else "below",
        "slopes": slopes,
        "distance_pct": dist,
        "overextended": bool(over),
        "events_recent": events[-8:],
        "structure": structure,
    }


def _divergence(d: pd.DataFrame, lookback: int) -> list[dict]:
    w = d.iloc[-lookback:]
    ph, pl = ind.pivots(w, 3)
    out = []
    lows = w.index[pl]
    if len(lows) >= 2:
        a, b = lows[-2], lows[-1]
        if w.at[b, "low"] < w.at[a, "low"] and w.at[b, "rsi"] > w.at[a, "rsi"]:
            out.append({"type": "Bullish divergence", "from": a.strftime("%Y-%m-%d"), "to": b.strftime("%Y-%m-%d"),
                        "detail": f"price lower low {w.at[a, 'low']:.2f} -> {w.at[b, 'low']:.2f}, RSI higher low {w.at[a, 'rsi']:.1f} -> {w.at[b, 'rsi']:.1f}"})
    highs = w.index[ph]
    if len(highs) >= 2:
        a, b = highs[-2], highs[-1]
        if w.at[b, "high"] > w.at[a, "high"] and w.at[b, "rsi"] < w.at[a, "rsi"]:
            out.append({"type": "Bearish divergence", "from": a.strftime("%Y-%m-%d"), "to": b.strftime("%Y-%m-%d"),
                        "detail": f"price higher high {w.at[a, 'high']:.2f} -> {w.at[b, 'high']:.2f}, RSI lower high {w.at[a, 'rsi']:.1f} -> {w.at[b, 'rsi']:.1f}"})
    return out


def _failure_swing(rsi: pd.Series, ob: float, os_: float, lookback: int = 40) -> str | None:
    s = rsi.dropna().iloc[-lookback:].to_numpy()
    if len(s) < 10:
        return None
    # bullish: dips below 30, bounces to peak P, pulls back staying above 30, then breaks P
    below = np.where(s < os_)[0]
    if len(below):
        j = below[-1]
        after = s[j + 1:]
        if len(after) > 3:
            pk = int(np.argmax(after[:-1]))
            trough = after[pk:-1].min() if pk < len(after) - 1 else None
            if trough is not None and trough > os_ and after[-1] > after[pk] and pk > 0:
                return "Bullish failure swing (RSI held above 30 on the retest and broke its prior peak)"
    above = np.where(s > ob)[0]
    if len(above):
        j = above[-1]
        after = s[j + 1:]
        if len(after) > 3:
            tr = int(np.argmin(after[:-1]))
            peak = after[tr:-1].max() if tr < len(after) - 1 else None
            if peak is not None and peak < ob and after[-1] < after[tr] and tr > 0:
                return "Bearish failure swing (RSI failed below 70 on the retest and broke its prior low)"
    return None


def rsi_analysis(d: pd.DataFrame, cfg: dict) -> dict:
    r = cfg["rsi"]
    s = d["rsi"]
    if pd.isna(s.iloc[-1]):
        return {"available": False, "reason": "Not enough candles for RSI 14."}
    v = s.iloc[-1]
    zone = ("Above 70 - potentially overbought (not an automatic sell)" if v > r["overbought"]
            else "50 to 70 - positive momentum, subject to trend" if v >= r["midline"]
            else "30 to 50 - weak momentum" if v >= r["oversold"]
            else "Below 30 - potentially oversold (not an automatic buy)")
    chg5 = v - s.iloc[-6] if len(s) > 6 else np.nan
    cross = None
    tail = s.iloc[-10:]
    for j in range(1, len(tail)):
        if tail.iloc[j - 1] < r["midline"] <= tail.iloc[j]:
            cross = f"Crossed above 50 on {tail.index[j]:%Y-%m-%d}"
        elif tail.iloc[j - 1] >= r["midline"] > tail.iloc[j]:
            cross = f"Crossed below 50 on {tail.index[j]:%Y-%m-%d}"
    return {
        "available": True, "value": _r(v, 1), "zone": zone,
        "direction": "rising" if chg5 > 1 else "falling" if chg5 < -1 else "flat",
        "change_5d": _r(chg5, 1), "midline_cross": cross,
        "divergences": _divergence(d, r["divergence_lookback"]),
        "failure_swing": _failure_swing(s, r["overbought"], r["oversold"]),
    }


def volume_analysis(d: pd.DataFrame, cfg: dict) -> dict:
    v = cfg["volume"]
    last = d.iloc[-1]
    if pd.isna(last.vol_avg) or last.vol_avg == 0:
        return {"available": False, "reason": "Need 20 sessions of volume."}
    w = d.iloc[-v["accumulation_window"]:]
    chg = w["close"].diff()
    up = w["volume"][chg > 0].mean()
    dn = w["volume"][chg < 0].mean()
    ratio = (up / dn) if dn and not np.isnan(dn) and not np.isnan(up) else np.nan
    pattern = ("Accumulation - up-day volume exceeds down-day volume" if ratio >= v["accumulation_ratio"]
               else "Distribution - down-day volume exceeds up-day volume" if ratio <= 1 / v["accumulation_ratio"]
               else "Neutral - no clear volume bias")
    hv = d.iloc[-20:]
    hv = hv[hv["volume"] >= v["high_volume_multiple"] * hv["vol_avg"]]
    exp = [{"date": i.strftime("%Y-%m-%d"), "x_avg": _r(r.volume / r.vol_avg),
            "move": "up" if r.close >= r.open else "down"} for i, r in hv.iterrows()]
    return {"available": True, "today": int(last.volume), "avg20": int(last.vol_avg),
            "ratio_to_avg": _r(last.volume / last.vol_avg), "updown_volume_ratio": _r(ratio),
            "pattern": pattern, "high_volume_days": exp}


def delivery_analysis(d: pd.DataFrame) -> dict:
    if "deliv_pct" not in d or d["deliv_pct"].dropna().empty:
        return {"available": False,
                "reason": "Delivery % not supplied. Zerodha Kite does not provide it; it comes from NSE's daily "
                          "security-wise delivery file (sec_bhavdata_full). Load it via data.nse_delivery."}
    s = d["deliv_pct"].dropna()
    chg = d["close"].diff()
    dd = d.loc[s.index]
    return {"available": True, "source": "NSE sec_bhavdata_full", "as_of": s.index[-1].strftime("%Y-%m-%d"),
            "current": _r(s.iloc[-1]), "avg5": _r(s.iloc[-5:].mean()), "avg10": _r(s.iloc[-10:].mean()),
            "avg20": _r(s.iloc[-20:].mean()),
            "on_up_days_20": _r(dd["deliv_pct"][chg.loc[s.index] > 0].iloc[-20:].mean()),
            "on_down_days_20": _r(dd["deliv_pct"][chg.loc[s.index] < 0].iloc[-20:].mean()),
            "note": "High delivery % alone is not proof of institutional accumulation."}


def gap_analysis(d: pd.DataFrame, cfg: dict) -> dict:
    g = cfg["gaps"]
    pc = d["close"].shift()
    gaps = []
    tail = d.iloc[-20:]
    for i, r in tail.iterrows():
        prev = pc.loc[i]
        if pd.isna(prev):
            continue
        pct = (r.open / prev - 1) * 100
        if abs(pct) >= g["significant_gap_pct"]:
            later = d.loc[i:]
            filled = bool((later["low"] <= prev).any()) if pct > 0 else bool((later["high"] >= prev).any())
            gaps.append({"date": i.strftime("%Y-%m-%d"), "prev_close": _r(prev), "open": _r(r.open), "gap_pct": _r(pct),
                         "direction": "gap-up" if pct > 0 else "gap-down", "filled": filled,
                         "volume_x_avg": _r(r.volume / r.vol_avg) if r.vol_avg else None})
    last = d.iloc[-1]
    today = (last.open / pc.iloc[-1] - 1) * 100 if not pd.isna(pc.iloc[-1]) else None
    return {"prev_close": _r(pc.iloc[-1]), "today_open": _r(last.open), "today_gap_pct": _r(today), "recent_gaps": gaps}


def trend_structure(d: pd.DataFrame, cfg: dict, levels: dict) -> dict:
    w = d.iloc[-cfg["support_resistance"]["lookback_days"]:]
    ph, pl = ind.pivots(w, cfg["support_resistance"]["pivot_bars"])
    hs = list(w["high"][ph].iloc[-3:])
    ls = list(w["low"][pl].iloc[-3:])
    lbl = "Not enough swing points"
    if len(hs) >= 2 and len(ls) >= 2:
        # swings within the S/R zone tolerance count as equal (double tops / bottoms)
        tol = levels.get("zone_tolerance") or 0.0

        def cmp(a, b):
            return 0 if abs(a - b) <= tol else (1 if a > b else -1)

        h, l = cmp(hs[-1], hs[-2]), cmp(ls[-1], ls[-2])
        lbl = {(1, 1): "Higher highs and higher lows (uptrend)",
               (-1, -1): "Lower highs and lower lows (downtrend)",
               (0, 0): "Equal highs and equal lows (sideways range)",
               (-1, 1): "Lower high with higher low (contracting / sideways)",
               (1, -1): "Higher high with lower low (expanding / volatile)",
               (0, 1): "Equal highs with a higher low (ascending triangle - pressure on resistance)",
               (0, -1): "Equal highs with a lower low (weakening)",
               (1, 0): "Higher high with equal lows (strengthening)",
               (-1, 0): "Lower high with equal lows (descending triangle - pressure on support)"}[(h, l)]
    notes = []
    last = d.iloc[-1]
    if levels.get("available"):
        rec = d.iloc[-10:]
        for z in levels["_zones"]:
            if any(rec["high"] > z.high) and last.close < z.low and z.level > last.close:
                notes.append(f"False breakout: price traded above {z.high:.2f} in the last 10 sessions but closed back below the zone")
        if levels.get("immediate_resistance") is None:
            notes.append("No resistance overhead in the last year of data (price discovery)")
        bl = levels.get("breakdown_level")
        if bl and last.close < bl:
            notes.append(f"Breakdown below {bl:.2f}")
    return {"swing_highs": [_r(x) for x in hs], "swing_lows": [_r(x) for x in ls], "structure": lbl, "notes": notes}


def weekly_snapshot(df: pd.DataFrame, cfg: dict) -> dict:
    w = ind.weekly(df)
    if len(w) < 30:
        return {"available": False, "reason": f"{len(w)} weekly candles; need 30+."}
    i = cfg["indicators"]
    c = w["close"]
    vals = {"ema21": ind.ema(c, i["ema_fast"]).iloc[-1], "ema63": ind.ema(c, i["ema_mid"]).iloc[-1],
            "ema200": ind.ema(c, i["ema_slow"]).iloc[-1]}
    out = {"available": True, "close": _r(c.iloc[-1]), "rsi": _r(ind.rsi(c, i["rsi_period"]).iloc[-1], 1)}
    for k, v in vals.items():
        out[k] = _r(v)
        out[f"price_vs_{k}"] = None if pd.isna(v) else ("above" if c.iloc[-1] > v else "below")
    return out


def analyse(df: pd.DataFrame, cfg: dict | None = None) -> dict:
    """Full technical picture as of the last candle in df."""
    cfg = cfg or config.load()
    d = prepare(df, cfg)
    levels = lv.find_levels(df, cfg)
    last = d.iloc[-1]
    return {
        "as_of": d.index[-1].strftime("%Y-%m-%d"),
        "candles_used": len(d),
        "close": _r(last.close),
        "atr": _r(last.atr),
        "ema": ema_analysis(d, cfg),
        "weekly": weekly_snapshot(df, cfg),
        "rsi": rsi_analysis(d, cfg),
        "candles": candles.detect(df, d["ema21"], cfg["indicators"]["candle_lookback"]),
        "volume": volume_analysis(d, cfg),
        "delivery": delivery_analysis(d),
        "levels": {k: v for k, v in levels.items() if k != "_zones"},
        "gaps": gap_analysis(d, cfg),
        "trend": trend_structure(d, cfg, levels),
    }
