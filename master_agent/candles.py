"""Candlestick patterns over the latest sessions (Master Instruction 3C).

Definitions are the standard textbook ones. Trend context (needed for hammer
vs hanging man, etc.) is judged from the close vs EMA 21 five bars earlier.
"""
from __future__ import annotations

import pandas as pd


def _parts(r):
    body = abs(r.close - r.open)
    rng = max(r.high - r.low, 1e-9)
    upper = r.high - max(r.close, r.open)
    lower = min(r.close, r.open) - r.low
    return body, rng, upper, lower


def detect(df: pd.DataFrame, ema21: pd.Series, lookback: int = 60, atr: pd.Series | None = None) -> list[dict]:
    if len(df) < 3:
        return []
    out = []
    start = max(2, len(df) - lookback)
    rows = list(df.itertuples())
    for i in range(start, len(df)):
        r, p, pp = rows[i], rows[i - 1], rows[i - 2]
        body, rng, up, lo = _parts(r)
        pbody, prng, _, _ = _parts(p)
        avg_body = (df["close"] - df["open"]).abs().iloc[max(0, i - 20):i].mean() or 1e-9
        prior_down = i >= 5 and df["close"].iloc[i - 1] < df["close"].iloc[i - 5]
        prior_up = i >= 5 and df["close"].iloc[i - 1] > df["close"].iloc[i - 5]
        found = []
        bull, bear = r.close > r.open, r.close < r.open
        if bull and p.close < p.open and r.close >= p.open and r.open <= p.close and body > pbody:
            found.append(("Bullish engulfing", "bullish"))
        if bear and p.close > p.open and r.open >= p.close and r.close <= p.open and body > pbody:
            found.append(("Bearish engulfing", "bearish"))
        if body <= 0.1 * rng:
            found.append(("Doji", "neutral"))
        elif lo >= 2 * body and up <= 0.3 * body + 0.1 * rng:
            found.append(("Hammer", "bullish") if prior_down else ("Hanging man", "bearish") if prior_up else ("Hammer-shaped candle", "neutral"))
        elif up >= 2 * body and lo <= 0.3 * body + 0.1 * rng:
            found.append(("Shooting star", "bearish") if prior_up else ("Inverted hammer", "bullish") if prior_down else ("Shooting-star-shaped candle", "neutral"))
        if r.high < p.high and r.low > p.low:
            found.append(("Inside bar", "neutral"))
        ppb, _, _, _ = _parts(pp)
        if pp.close < pp.open and ppb > avg_body and pbody < 0.5 * ppb and bull and r.close > (pp.open + pp.close) / 2:
            found.append(("Morning star", "bullish"))
        if pp.close > pp.open and ppb > avg_body and pbody < 0.5 * ppb and bear and r.close < (pp.open + pp.close) / 2:
            found.append(("Evening star", "bearish"))
        if bull and body >= 2 * avg_body and up <= 0.25 * body and r.close >= df["high"].iloc[max(0, i - 20):i].max():
            found.append(("Strong breakout candle", "bullish"))
        if up >= 0.6 * rng and rng >= 1.2 * prng:
            found.append(("Long upper wick (rejection)", "bearish"))
        if lo >= 0.6 * rng and rng >= 1.2 * prng:
            found.append(("Long lower wick (rejection)", "bullish"))
        for name, bias in found:
            ctx = "above EMA 21" if r.close > ema21.iloc[i] else "below EMA 21"
            out.append({"date": df.index[i].strftime("%Y-%m-%d"), "pattern": name, "bias": bias,
                        "close": round(r.close, 2), "context": ctx})
    return out
