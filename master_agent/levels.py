"""Support and resistance from actual swing highs / lows (Master Instruction 3F).

Every level returned carries the swing points (date, price) that created it, so
a level can always be checked on the chart. Nothing is interpolated or invented:
a zone exists only where price actually turned at least once.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

import pandas as pd

from . import config, indicators as ind


@dataclass
class Touch:
    date: str
    price: float
    kind: str          # "swing high" or "swing low"


@dataclass
class Zone:
    low: float
    high: float
    level: float
    touches: list[Touch] = field(default_factory=list)
    weekly_confirmed: bool = False

    @property
    def count(self) -> int:
        return len(self.touches)

    @property
    def role_reversal(self) -> bool:
        return len({t.kind for t in self.touches}) == 2

    @property
    def last_touch(self) -> str:
        return max(t.date for t in self.touches)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.update(count=self.count, role_reversal=self.role_reversal, last_touch=self.last_touch)
        return d


def _cluster(points: list[tuple[pd.Timestamp, float, str]], tol: float) -> list[Zone]:
    zones: list[Zone] = []
    cur: list = []
    for p in sorted(points, key=lambda x: x[1]):
        if cur and p[1] - cur[0][1] > 2 * tol:
            zones.append(cur)
            cur = []
        if cur and p[1] - cur[-1][1] > tol:
            zones.append(cur)
            cur = []
        cur.append(p)
    if cur:
        zones.append(cur)
    out = []
    for z in zones:
        prices = [p[1] for p in z]
        out.append(Zone(
            low=round(min(prices), 2), high=round(max(prices), 2),
            level=round(sum(prices) / len(prices), 2),
            touches=[Touch(p[0].strftime("%Y-%m-%d"), round(p[1], 2), p[2]) for p in sorted(z)],
        ))
    return out


def find_levels(df: pd.DataFrame, cfg: dict | None = None) -> dict:
    """Support/resistance for the last bar of df (no look-ahead)."""
    cfg = (cfg or config.load())
    sr = cfg["support_resistance"]
    if len(df) < 2 * sr["pivot_bars"] + 20:
        return {"available": False, "reason": f"Need at least {2 * sr['pivot_bars'] + 20} daily candles, have {len(df)}."}

    win = df.iloc[-sr["lookback_days"]:]
    close = float(df["close"].iloc[-1])
    atr = float(ind.atr(df, cfg["indicators"]["atr_period"]).iloc[-1])
    tol = max(sr["zone_tolerance_atr"] * atr, sr["zone_tolerance_min_pct"] / 100 * close)

    ph, pl = ind.pivots(win, sr["pivot_bars"])
    pts = [(d, float(win.at[d, "high"]), "swing high") for d in win.index[ph]]
    pts += [(d, float(win.at[d, "low"]), "swing low") for d in win.index[pl]]
    zones = _cluster(pts, tol)

    # weekly swing points that fall inside a daily zone confirm it
    wk = ind.weekly(win)
    if len(wk) > 2 * sr["weekly_pivot_bars"]:
        wh, wl = ind.pivots(wk, sr["weekly_pivot_bars"])
        wpts = list(wk["high"][wh]) + list(wk["low"][wl])
        for z in zones:
            z.weekly_confirmed = any(z.low - tol / 2 <= p <= z.high + tol / 2 for p in wpts)

    def strength(z: Zone) -> float:
        return z.count + (1 if z.weekly_confirmed else 0)

    supports = sorted([z for z in zones if z.level < close], key=lambda z: -z.level)
    resistances = sorted([z for z in zones if z.level >= close], key=lambda z: z.level)
    strong_n = sr["strong_min_touches"]

    def pick_strong(zs: list[Zone], skip: Zone | None):
        for z in zs:
            if z is not skip and strength(z) >= strong_n:
                return z
        rest = [z for z in zs if z is not skip]
        return max(rest, key=strength) if rest else None

    imm_s = supports[0] if supports else None
    imm_r = resistances[0] if resistances else None
    hi52 = float(win["high"].max())
    lo52 = float(win["low"].min())

    last_sh = win.index[ph][-1] if ph.any() else None
    last_sl = win.index[pl][-1] if pl.any() else None

    cons = win.iloc[-sr["consolidation_bars"]:]
    c_hi, c_lo = float(cons["high"].max()), float(cons["low"].min())
    consolidation = None
    if c_hi - c_lo <= sr["consolidation_max_atr"] * atr:
        consolidation = {"low": round(c_lo, 2), "high": round(c_hi, 2), "bars": len(cons),
                         "from": cons.index[0].strftime("%Y-%m-%d")}

    def zd(z):
        return z.to_dict() if z else None

    m = sr["max_levels_each_side"]
    return {
        "available": True,
        "as_of": df.index[-1].strftime("%Y-%m-%d"),
        "close": round(close, 2),
        "atr": round(atr, 2),
        "zone_tolerance": round(tol, 2),
        "immediate_support": zd(imm_s),
        "strong_support": zd(pick_strong(supports, imm_s)),
        "immediate_resistance": zd(imm_r),
        "major_resistance": zd(pick_strong(resistances, imm_r)),
        "supports": [z.to_dict() for z in supports[:m]],
        "resistances": [z.to_dict() for z in resistances[:m]],
        "high_52w": round(hi52, 2),
        "low_52w": round(lo52, 2),
        "price_discovery": imm_r is None,
        "last_swing_high": {"date": last_sh.strftime("%Y-%m-%d"), "price": round(float(win.at[last_sh, "high"]), 2)} if last_sh is not None else None,
        "last_swing_low": {"date": last_sl.strftime("%Y-%m-%d"), "price": round(float(win.at[last_sl, "low"]), 2)} if last_sl is not None else None,
        "consolidation": consolidation,
        "breakout_level": round(imm_r.high, 2) if imm_r else None,
        "breakdown_level": round(imm_s.low, 2) if imm_s else None,
        "_zones": zones,
    }
