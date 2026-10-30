"""Yahoo Finance daily candles (split-adjusted, not dividend-adjusted). Free, no login."""
from __future__ import annotations

import pandas as pd

from . import normalise

SOURCE = "Yahoo Finance (NSE)"


def daily(symbol: str, start: str, end: str | None = None) -> pd.DataFrame:
    import yfinance as yf
    t = symbol if "." in symbol or symbol.startswith("^") else f"{symbol}.NS"
    df = yf.Ticker(t).history(start=start, end=end, interval="1d", auto_adjust=False)
    if df.empty:
        raise LookupError(f"No Yahoo data for {t}")
    return normalise(df.reset_index().rename(columns={"Date": "date"}))
