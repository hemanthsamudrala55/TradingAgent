"""Personalised Screener.in dashboard (Master Instruction Module 1) and valuation.

Values are parsed from the public Screener.in company page. Metrics Screener
only shows to logged-in users as custom ratios (ROIC, pledged %, cash cycle on
some pages, industry P/E) are reported as Unavailable unless found on the page.
Nothing is estimated in place of a missing value.
"""
from __future__ import annotations

import math
import re
from datetime import date

UNAVAILABLE = "Unavailable"

# Order fixed by the Master Instruction (Module 1A) + Face Value.
DASHBOARD = [
    ("Valuation", "Market Capitalization"), ("Valuation", "Current Market Price"), ("Valuation", "52-Week High / Low"),
    ("Valuation", "Stock P/E"), ("Valuation", "Industry P/E"), ("Valuation", "Book Value"),
    ("Valuation", "Price to Sales"), ("Valuation", "PEG Ratio"), ("Valuation", "Dividend Yield"),
    ("Valuation", "Intrinsic Value"), ("Valuation", "Graham Number"), ("Valuation", "Face Value"),
    ("Financial Strength", "Debt"), ("Financial Strength", "Reserves"), ("Financial Strength", "Debt-to-Equity"),
    ("Financial Strength", "Cash Cycle"),
    ("Profitability", "ROCE"), ("Profitability", "ROE"), ("Profitability", "ROIC"), ("Profitability", "OPM"),
    ("Ownership", "Promoter Holding"), ("Ownership", "Pledged Percentage"), ("Ownership", "Change in Promoter Holding"),
    ("Ownership", "Change in FII Holding"), ("Ownership", "Change in DII Holding"),
    ("Performance", "QoQ Sales Growth"), ("Performance", "QoQ Sales Variation"),
]

_TOP = {"market cap": "Market Capitalization", "current price": "Current Market Price", "high / low": "52-Week High / Low",
        "stock p/e": "Stock P/E", "industry pe": "Industry P/E", "industry p/e": "Industry P/E", "book value": "Book Value",
        "price to sales": "Price to Sales", "peg ratio": "PEG Ratio", "dividend yield": "Dividend Yield",
        "intrinsic value": "Intrinsic Value (Screener)", "graham number": "Graham Number (Screener)",
        "face value": "Face Value", "debt": "Debt", "reserves": "Reserves", "debt to equity": "Debt-to-Equity",
        "cash conversion cycle": "Cash Cycle", "roce": "ROCE", "roe": "ROE", "roic": "ROIC", "opm": "OPM",
        "promoter holding": "Promoter Holding", "pledged percentage": "Pledged Percentage",
        "change in prom hold": "Change in Promoter Holding", "chg in fii hold": "Change in FII Holding",
        "chg in dii hold": "Change in DII Holding", "qoq sales": "QoQ Sales Growth", "sales growth": "Sales Growth 3Y",
        "eps": "EPS"}


def _num(s: str) -> float | None:
    m = re.search(r"-?[\d,]*\.?\d+", s.replace("₹", ""))
    return float(m.group().replace(",", "")) if m else None


def _table(soup, section_id: str) -> dict[str, list[str]]:
    sec = soup.find(id=section_id)
    if not sec or not sec.find("table"):
        return {}
    t = sec.find("table")
    heads = [th.get_text(strip=True) for th in t.find("thead").find_all("th")] if t.find("thead") else []
    rows = {"_cols": heads[1:]}
    for tr in t.find("tbody").find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if cells:
            rows[re.sub(r"[\s+ ]+$", "", cells[0]).strip()] = cells[1:]
    return rows


def parse_screener(html: str) -> dict:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    out: dict = {"name": (soup.find("h1").get_text(strip=True) if soup.find("h1") else None), "raw": {}}
    for li in soup.select("#top-ratios li"):
        n = li.select_one(".name")
        v = li.select_one(".value")
        if not n or not v:
            continue
        key = _TOP.get(n.get_text(" ", strip=True).lower())
        if key:
            out["raw"][key] = " ".join(v.get_text(" ", strip=True).split())
    out["quarters"] = _table(soup, "quarters")
    out["profit_loss"] = _table(soup, "profit-loss")
    out["balance_sheet"] = _table(soup, "balance-sheet")
    out["ratios"] = _table(soup, "ratios")
    out["shareholding"] = _table(soup, "quarterly-shp") or _table(soup, "shareholding")
    return out


def fetch_screener(symbol: str) -> dict:
    import requests
    for path in (f"/company/{symbol}/consolidated/", f"/company/{symbol}/"):
        r = requests.get("https://www.screener.in" + path, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        if r.status_code == 200 and "top-ratios" in r.text:
            d = parse_screener(r.text)
            d["url"] = r.url
            return d
    raise LookupError(f"Screener.in page not found for {symbol}")


def graham_number(eps: float | None, bvps: float | None) -> dict:
    if eps is None or bvps is None:
        return {"value": None, "reason": "EPS or book value per share unavailable"}
    if eps <= 0 or bvps <= 0:
        return {"value": None, "eps": eps, "bvps": bvps, "reason": "Graham Number is undefined for negative EPS or book value"}
    return {"value": round(math.sqrt(22.5 * eps * bvps), 2), "eps": eps, "bvps": bvps,
            "formula": f"sqrt(22.5 x {eps} x {bvps})"}


def dcf(fcf_base: float, shares: float, growth_pct: float, years: int, discount_pct: float,
        terminal_pct: float, net_debt: float = 0.0) -> dict:
    """Two-stage DCF per share. All money inputs in the same unit (e.g. Rs crore)."""
    r, g, tg = discount_pct / 100, growth_pct / 100, terminal_pct / 100
    if r <= tg:
        return {"value": None, "reason": "Discount rate must exceed terminal growth"}
    fcfs = [fcf_base * (1 + g) ** t for t in range(1, years + 1)]
    pv = sum(f / (1 + r) ** t for t, f in enumerate(fcfs, 1))
    tv = fcfs[-1] * (1 + tg) / (r - tg)
    ev = pv + tv / (1 + r) ** years
    return {"value": round((ev - net_debt) / shares, 2), "pv_explicit": round(pv, 2),
            "pv_terminal": round(tv / (1 + r) ** years, 2), "terminal_share_pct": round(tv / (1 + r) ** years / ev * 100, 1)}


def dcf_sensitivity(base: dict, discounts=(-2, -1, 0, 1, 2), terminals=(-1, 0, 1)) -> list[dict]:
    rows = []
    for dd in discounts:
        row = {"discount_pct": base["discount_pct"] + dd}
        for tt in terminals:
            v = dcf(**{**base, "discount_pct": base["discount_pct"] + dd, "terminal_pct": base["terminal_pct"] + tt})
            row[f"tg {base['terminal_pct'] + tt}%"] = v["value"]
        rows.append(row)
    return rows


def _last(row: list[str] | None, n=1):
    return [_num(x) for x in row[-n:]] if row else [None] * n


def dashboard(data: dict, source: str = "Screener.in") -> dict:
    raw = data.get("raw", {})
    vals = {k: raw.get(k) for _, k in DASHBOARD}
    notes = {}

    # Shareholding changes - latest quarter vs previous
    shp = data.get("shareholding", {})
    for label, key in (("Promoters", "Change in Promoter Holding"), ("FIIs", "Change in FII Holding"), ("DIIs", "Change in DII Holding")):
        row = next((v for k, v in shp.items() if k.lower().startswith(label.lower())), None)
        if not vals.get(key) and row and len(row) >= 2:
            a, b = _last(row, 2)
            if a is not None and b is not None:
                vals[key] = f"{b - a:+.2f} pts (QoQ)"
                notes[key] = f"{shp['_cols'][-2]} -> {shp['_cols'][-1]}"
        if key == "Change in Promoter Holding" and not vals.get("Promoter Holding") and row:
            vals["Promoter Holding"] = f"{_last(row)[0]} %"

    q = data.get("quarters", {})
    sales = q.get("Sales") or q.get("Revenue")
    if sales and len(sales) >= 2:
        a, b = _last(sales, 2)
        if a:
            vals["QoQ Sales Growth"] = vals.get("QoQ Sales Growth") or f"{(b / a - 1) * 100:.2f} %"
            vals["QoQ Sales Variation"] = f"Rs {b - a:,.0f} Cr ({q['_cols'][-2]} -> {q['_cols'][-1]})"
    opm = q.get("OPM %")
    if opm and not vals.get("OPM"):
        vals["OPM"] = opm[-1]

    # Graham Number from TTM EPS and Book Value
    pl = data.get("profit_loss", {})
    eps = _last(pl.get("EPS in Rs"))[0] if pl.get("EPS in Rs") else _num(raw.get("EPS", "") or "")
    bv = _num(raw.get("Book Value") or "")
    g = graham_number(eps, bv)
    vals["Graham Number"] = f"Rs {g['value']:,}" if g.get("value") else None
    notes["Graham Number"] = g.get("formula") or g.get("reason")
    if raw.get("Intrinsic Value (Screener)"):
        vals["Intrinsic Value"] = raw["Intrinsic Value (Screener)"] + " (Screener custom ratio - verify method)"
    else:
        notes["Intrinsic Value"] = "Not calculated automatically: enter FCF and assumptions in the DCF panel."

    rows = [{"category": c, "metric": m, "value": vals.get(m) or UNAVAILABLE, "note": notes.get(m, "")} for c, m in DASHBOARD]
    cmp = _num(raw.get("Current Market Price") or "")
    return {"name": data.get("name"), "source": source, "url": data.get("url"), "observed": date.today().isoformat(),
            "rows": rows, "graham": g, "cmp": cmp,
            "graham_margin_of_safety_pct": round((g["value"] / cmp - 1) * 100, 1) if g.get("value") and cmp else None,
            "unavailable": [r["metric"] for r in rows if r["value"] == UNAVAILABLE]}
