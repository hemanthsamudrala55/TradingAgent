"""Indicator maths. Inputs are DataFrames with open/high/low/close/volume columns."""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def rma(s: pd.Series, n: int) -> pd.Series:
    """Wilder smoothing seeded with the simple average of the first n values
    (TradingView ta.rma / Kite charts), so values match those platforms."""
    v = s.to_numpy(float)
    out = np.full(len(v), np.nan)
    valid = np.flatnonzero(~np.isnan(v))
    if len(valid) < n:
        return pd.Series(out, s.index)
    first = valid[0] + n - 1
    out[first] = v[valid[0]:first + 1].mean()
    for i in range(first + 1, len(v)):
        out[i] = (out[i - 1] * (n - 1) + v[i]) / n
    return pd.Series(out, s.index)


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """Wilder's RSI."""
    d = close.diff()
    gain = rma(d.clip(lower=0), n)
    loss = rma(-d.clip(upper=0), n)
    rs = gain / loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.where(loss != 0, 100.0).where(gain.notna())


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev = df["close"].shift()
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1).max(axis=1)
    tr.iloc[0] = df["high"].iloc[0] - df["low"].iloc[0]
    return rma(tr, n)


def weekly(df: pd.DataFrame) -> pd.DataFrame:
    """Resample daily candles to weeks ending Friday (NSE convention)."""
    w = df.resample("W-FRI").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    return w.dropna(subset=["close"])


def pivots(df: pd.DataFrame, k: int) -> tuple[pd.Series, pd.Series]:
    """Swing highs / lows: bar is the extreme of k bars on each side.

    A pivot at bar i is only known at bar i+k, so callers that simulate must
    only use pivots whose index is <= today - k (handled automatically when the
    frame is cut at 'today', because the last k bars can never qualify).
    """
    h, l = df["high"].to_numpy(), df["low"].to_numpy()
    n = len(df)
    ph = np.zeros(n, bool)
    pl = np.zeros(n, bool)
    for i in range(k, n - k):
        win_h = h[i - k:i + k + 1]
        win_l = l[i - k:i + k + 1]
        # ties (double tops at the same price) count once, on the first bar
        if h[i] == win_h.max() and not (h[i - k:i] == h[i]).any():
            ph[i] = True
        if l[i] == win_l.min() and not (l[i - k:i] == l[i]).any():
            pl[i] = True
    return pd.Series(ph, df.index), pd.Series(pl, df.index)
