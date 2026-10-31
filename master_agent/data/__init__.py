"""Market-data providers. Every frame: DatetimeIndex, columns open/high/low/close/volume."""
from __future__ import annotations

import io

import pandas as pd

COLS = ["open", "high", "low", "close", "volume"]
_ALIASES = {"date": "date", "datetime": "date", "timestamp": "date", "time": "date",
            "open": "open", "open price": "open", "high": "high", "high price": "high",
            "low": "low", "low price": "low", "close": "close", "close price": "close", "ltp": "close",
            "volume": "volume", "vol": "volume", "total traded quantity": "volume", "shares traded": "volume",
            "deliv_per": "deliv_pct", "% dly qt to traded qty": "deliv_pct", "deliverable %": "deliv_pct"}


def _dates(idx) -> pd.DatetimeIndex:
    """ISO (2024-01-02) and datetimes first; day-first text (02-01-2024, 02-Jan-2024) as NSE/Excel write it."""
    if isinstance(idx, pd.DatetimeIndex):
        return idx
    iso = pd.to_datetime(idx, format="ISO8601", errors="coerce")
    if iso.notna().mean() > 0.95:
        return iso
    return pd.to_datetime(idx, dayfirst=True, errors="coerce", format="mixed")


def normalise(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=lambda c: _ALIASES.get(str(c).strip().lower(), str(c).strip().lower()))
    if "date" in df.columns:
        df = df.set_index("date")
    df.index = _dates(df.index)
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    df.index = df.index.normalize()
    missing = [c for c in COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Chart data is missing columns: {missing}")
    for c in COLS + (["deliv_pct"] if "deliv_pct" in df else []):
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", ""), errors="coerce")
    df = df[~df.index.isna()].dropna(subset=["close"]).sort_index()
    return df[~df.index.duplicated(keep="last")][COLS + (["deliv_pct"] if "deliv_pct" in df else [])]


def normalise_hourly(df: pd.DataFrame) -> pd.DataFrame:
    """Like normalise, but keeps the time of day, as Indian clock time."""
    df = df.rename(columns=lambda c: str(c).strip().lower()).rename(columns={"datetime": "date"})
    idx = pd.to_datetime(df["date"], utc=True).dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
    df = df.set_index(pd.DatetimeIndex(idx))[COLS].apply(pd.to_numeric, errors="coerce")
    df = df.dropna(subset=["close"]).sort_index()
    return df[~df.index.duplicated(keep="last")]


def read_csv(src) -> pd.DataFrame:
    """CSV exported from Kite / TradingView / NSE / Excel. src: path or bytes."""
    if isinstance(src, (bytes, bytearray)):
        src = io.BytesIO(src)
    return normalise(pd.read_csv(src))
