"""Candle sizes for the simple view: Month, Quarter, Half-year and Year are built from daily candles."""
from __future__ import annotations

import pandas as pd

FRAMES = ("Hour", "Day", "Month", "Quarter", "Half-year", "Year")
_AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
_LABEL = {"Hour": "%d %b %Y %H:%M", "Day": "%d %b %Y", "Month": "%b %Y", "Year": "%Y"}


def resample(daily: pd.DataFrame, frame: str) -> pd.DataFrame:
    """One row per calendar period, indexed by the period's first trading day. The newest may be unfinished."""
    if frame == "Day":
        return daily[list(_AGG)]
    idx = daily.index
    key = {"Month": idx.to_period("M"), "Quarter": idx.to_period("Q"), "Year": idx.year,
           "Half-year": idx.year * 10 + (idx.month > 6)}[frame]
    g = daily.groupby(key)
    out = g.agg(_AGG)
    out.index = g.apply(lambda x: x.index[0], include_groups=False).values
    return out


def label(ts: pd.Timestamp, frame: str) -> str:
    if frame == "Quarter":
        return f"Q{ts.quarter} {ts.year}"
    if frame == "Half-year":
        return f"{'Jan-Jun' if ts.month <= 6 else 'Jul-Dec'} {ts.year}"
    return ts.strftime(_LABEL[frame])


def payload(df: pd.DataFrame, frame: str) -> list[dict]:
    """Chart rows. Times are Indian clock time written as UTC, so the chart shows them unshifted."""
    return [{"time": int(ts.timestamp()), "label": label(ts, frame), "open": round(float(r.open), 2),
             "high": round(float(r.high), 2), "low": round(float(r.low), 2), "close": round(float(r.close), 2),
             "volume": float(r.volume)} for ts, r in zip(df.index, df.itertuples())]
