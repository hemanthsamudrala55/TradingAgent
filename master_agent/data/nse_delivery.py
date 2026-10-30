"""Delivery % from NSE's security-wise bhavcopy (sec_bhavdata_full_DDMMYYYY.csv).

One file per trading day; files are cached under state/nse_cache. NSE blocks
requests without browser-like headers, so a session cookie is fetched first.
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pandas as pd

SOURCE = "NSE India - sec_bhavdata_full"
CACHE = Path(__file__).resolve().parents[2] / "state" / "nse_cache"
URL = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{d:%d%m%Y}.csv"
HEAD = {"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*", "Referer": "https://www.nseindia.com/"}


def _day(d, sess) -> pd.DataFrame | None:
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{d:%Y%m%d}.csv"
    if not f.exists():
        r = sess.get(URL.format(d=d), headers=HEAD, timeout=20)
        if r.status_code != 200 or b"SYMBOL" not in r.content[:200]:
            return None
        f.write_bytes(r.content)
    df = pd.read_csv(f)
    df.columns = [c.strip() for c in df.columns]
    return df


def delivery_series(symbol: str, dates: pd.DatetimeIndex) -> pd.Series:
    import requests
    sess = requests.Session()
    sess.get("https://www.nseindia.com", headers=HEAD, timeout=20)
    out = {}
    for d in dates:
        df = _day(d, sess)
        if df is None:
            continue
        row = df[(df["SYMBOL"].str.strip() == symbol) & (df["SERIES"].str.strip() == "EQ")]
        if not row.empty:
            v = pd.to_numeric(str(row["DELIV_PER"].iloc[0]).strip(), errors="coerce")
            out[d] = v
    return pd.Series(out, dtype=float, name="deliv_pct")


def attach(df: pd.DataFrame, symbol: str, days: int = 30) -> pd.DataFrame:
    """Adds deliv_pct for the last `days` sessions. Leaves df unchanged if NSE is unreachable."""
    try:
        s = delivery_series(symbol, df.index[-days:])
    except Exception:  # noqa: BLE001 - delivery is optional; report as unavailable
        return df
    out = df.copy()
    out["deliv_pct"] = s.reindex(out.index)
    return out
