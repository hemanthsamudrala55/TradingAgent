"""Yahoo Finance daily candles (split-adjusted, not dividend-adjusted). Free, no login."""
from __future__ import annotations

import pandas as pd

from . import normalise, normalise_hourly

SOURCE = "Yahoo Finance (NSE)"


def hourly(symbol: str) -> pd.DataFrame:
    """Yahoo keeps about two years of hourly candles."""
    import yfinance as yf
    t = symbol if "." in symbol or symbol.startswith("^") else f"{symbol}.NS"
    df = yf.Ticker(t).history(period="730d", interval="60m", auto_adjust=False)
    if df.empty:
        raise LookupError(f"No Yahoo hourly data for {t}")
    return normalise_hourly(df.reset_index())


def daily(symbol: str, start: str, end: str | None = None) -> pd.DataFrame:
    import yfinance as yf
    t = symbol if "." in symbol or symbol.startswith("^") else f"{symbol}.NS"
    df = yf.Ticker(t).history(start=start, end=end, interval="1d", auto_adjust=False)
    if df.empty:
        raise LookupError(f"No Yahoo data for {t}")
    return normalise(df.reset_index().rename(columns={"Date": "date"}))


def ltp(symbols: list[str]) -> dict[str, dict]:
    """Latest traded price per symbol from 1-minute candles: {sym: {"price", "time"}}. Yahoo's NSE
    prices can be a few minutes late. Symbols Yahoo cannot price are left out."""
    from concurrent.futures import ThreadPoolExecutor
    import yfinance as yf

    def one(sym):
        t = sym if "." in sym or sym.startswith("^") else f"{sym}.NS"
        df = yf.Ticker(t).history(period="5d", interval="1m", auto_adjust=False)
        df = df.dropna(subset=["Close"])
        if df.empty:
            return sym, None
        return sym, {"price": round(float(df["Close"].iloc[-1]), 2), "time": df.index[-1].isoformat()}

    with ThreadPoolExecutor(6) as ex:
        return {s: q for s, q in ex.map(one, symbols) if q}
