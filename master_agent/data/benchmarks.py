"""Benchmark series: Nifty Total Return Indices and mutual-fund NAVs.

* Nifty TRI  - niftyindices.com (official). If the site is unreachable, drop a
  CSV exported from niftyindices.com at state/benchmarks/<id>.csv
  (columns Date, Total Returns Index / Close).
* Fund NAV   - AMFI data via api.mfapi.in. The scheme is resolved by name and the
  plan words in config (e.g. Direct + Growth), so plans are never mixed.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

CACHE = Path(__file__).resolve().parents[2] / "state" / "benchmarks"
TRI_URL = "https://www.niftyindices.com/Backpage.aspx/getTotalReturnIndexString"
HEAD = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json; charset=UTF-8",
        "Referer": "https://www.niftyindices.com/reports/historical-data", "X-Requested-With": "XMLHttpRequest"}


def _from_csv(bid: str) -> pd.Series | None:
    f = CACHE / f"{bid}.csv"
    if not f.exists():
        return None
    df = pd.read_csv(f)
    df.columns = [c.strip().lower() for c in df.columns]
    vcol = next(c for c in df.columns if c in ("total returns index", "totalreturnsindex", "tri", "nav", "close", "value"))
    s = pd.Series(pd.to_numeric(df[vcol].astype(str).str.replace(",", ""), errors="coerce").values,
                  index=pd.to_datetime(df["date"], dayfirst=True, errors="coerce"))
    return s.dropna().sort_index()


def nifty_tri(index_name: str, start: str, end: str) -> pd.Series:
    import requests
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    out = []
    sess = requests.Session()
    sess.get("https://www.niftyindices.com/reports/historical-data", headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    while s <= e:                       # the site returns at most ~1 year per request
        ce = min(s + pd.Timedelta(days=364), e)
        cinfo = "{'name':'%s','startDate':'%s','endDate':'%s','indexName':'%s'}" % (
            index_name, s.strftime("%d-%b-%Y"), ce.strftime("%d-%b-%Y"), index_name)
        r = sess.post(TRI_URL, headers=HEAD, data=json.dumps({"cinfo": cinfo}), timeout=30)
        r.raise_for_status()
        out += json.loads(r.json()["d"])
        s = ce + pd.Timedelta(days=1)
    if not out:
        raise LookupError(f"No TRI data returned for {index_name}")
    df = pd.DataFrame(out)
    vcol = next(c for c in df.columns if "return" in c.lower())
    dcol = next(c for c in df.columns if "date" in c.lower())
    return pd.Series(pd.to_numeric(df[vcol], errors="coerce").values,
                     index=pd.to_datetime(df[dcol], errors="coerce")).dropna().sort_index()


def resolve_fund(search: str, must: list[str]) -> tuple[int, str]:
    import requests
    res = requests.get("https://api.mfapi.in/mf/search", params={"q": search}, timeout=20).json()
    for r in res:
        name = r["schemeName"].lower()
        if search.lower() in name and all(m.lower() in name for m in must) and "idcw" not in name and "dividend" not in name:
            return int(r["schemeCode"]), r["schemeName"]
    raise LookupError(f"No scheme matching '{search}' with {must}")


def fund_nav(code: int) -> pd.Series:
    import requests
    data = requests.get(f"https://api.mfapi.in/mf/{code}", timeout=30).json()["data"]
    return pd.Series([float(x["nav"]) for x in data],
                     index=pd.to_datetime([x["date"] for x in data], format="%d-%m-%Y")).sort_index()


def series(bench: dict, start: str, end: str) -> tuple[pd.Series, dict]:
    """Returns (values, meta). meta names the exact source / scheme used."""
    s = _from_csv(bench["id"])
    if s is not None:
        return s, {"source": f"local file state/benchmarks/{bench['id']}.csv", "name": bench["name"]}
    if bench["kind"] == "nifty_tri":
        return nifty_tri(bench["index_name"], start, end), {"source": "niftyindices.com (Total Returns Index)", "name": bench["name"]}
    if bench["kind"] == "mf_nav":
        code, name = resolve_fund(bench["search"], bench.get("plan_must_contain", []))
        return fund_nav(code), {"source": f"AMFI NAV via mfapi.in, scheme code {code}", "name": name}
    raise ValueError(bench["kind"])
