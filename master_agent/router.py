"""Intelligent query understanding (Master Instruction section 2 and 5).

Turns a natural-language question into the analysis mode and the exact
sections to show, so the agent answers only what was asked.
"""
from __future__ import annotations

import re

MODES = {
    "A": "Fundamental analysis only",
    "B": "Technical analysis only",
    "C": "Combined analysis",
    "D": "Specific data only",
    "E": "Comparative analysis",
    "F": "Positional trading analysis",
    "V": "Valuation only",
    "P": "Portfolio performance vs benchmarks",
    "Q": "Quick update",
}

# metric keyword -> (section, key) used by selective mode D
METRICS = {
    r"\broce\b": ("fund", "ROCE"), r"\broe\b": ("fund", "ROE"), r"\broic\b": ("fund", "ROIC"),
    r"debt[- ]to[- ]equity|\bd/e\b": ("fund", "Debt-to-Equity"), r"\bdebt\b(?![- ]to)": ("fund", "Debt"),
    r"\bopm\b|operating (profit )?margin": ("fund", "OPM"), r"\bp/?e\b": ("fund", "Stock P/E"),
    r"promoter": ("fund", "Promoter Holding"), r"pledg": ("fund", "Pledged Percentage"),
    r"\bfii\b": ("fund", "Change in FII Holding"), r"\bdii\b": ("fund", "Change in DII Holding"),
    r"graham": ("fund", "Graham Number"), r"book value": ("fund", "Book Value"),
    r"dividend": ("fund", "Dividend Yield"), r"market cap": ("fund", "Market Capitalization"),
    r"quarter": ("fund", "quarters"),
    r"\bema\b|\bema ?(21|63|200)\b": ("tech", "ema"), r"\brsi\b": ("tech", "rsi"),
    r"support|resistance|\blevels?\b": ("tech", "levels"), r"volume": ("tech", "volume"),
    r"delivery": ("tech", "delivery"), r"\bgaps?\b|gap[- ]?(up|down)": ("tech", "gaps"),
    r"candle|pattern": ("tech", "candles"), r"trend structure|higher high|lower low": ("tech", "trend"),
}

_STOP = {"THE", "AND", "FOR", "RSI", "EMA", "ROE", "ROCE", "ROIC", "OPM", "FII", "DII", "PE", "SHOW", "ME", "GIVE",
         "ONLY", "VS", "WITH", "NSE", "BSE", "TRI", "NIFTY", "IS", "IT", "OF", "MY", "A", "I", "AN", "TO", "IN", "ON"}


def symbols_in(q: str) -> list[str]:
    return [t for t in re.findall(r"\b[A-Z][A-Z0-9&-]{1,19}\b", q) if t not in _STOP]


def route(query: str, symbol: str | None = None) -> dict:
    q = (query or "").strip()
    ql = q.lower()
    syms = symbols_in(q)
    if symbol:
        syms = [symbol.upper()] + [s for s in syms if s != symbol.upper()]
    metrics = []
    for pat, m in METRICS.items():
        if re.search(pat, ql) and m not in metrics:
            metrics.append(m)
    detail = bool(re.search(r"in detail|detailed|explain", ql))

    def out(mode, sections, **kw):
        return {"mode": mode, "mode_name": MODES[mode], "symbols": syms, "sections": sections,
                "metrics": metrics, "detail": detail, "query": q, **kw}

    if re.search(r"portfolio|benchmark|smallcap|small cap|motilal|outperform|invested|worth today|best and worst|my (stocks|holdings)", ql):
        return out("P", ["portfolio"])
    if re.search(r"\bcompare\b|\bvs\.?\b|versus", ql) and len(syms) >= 2:
        return out("E", ["compare"])
    if re.search(r"position(al)?|swing|trade|entry|stop[- ]?loss|target|risk[- ]reward", ql):
        return out("F", ["chart", "positional", "ema", "rsi", "volume", "levels", "gaps", "trend"])
    if re.search(r"complete|full analysis|both|good investment|everything", ql):
        return out("C", ["dashboard", "fundamental", "chart", "technical", "positional", "conclusion"])
    if re.search(r"overvalued|undervalued|valuation|intrinsic|fair value", ql):
        return out("V", ["valuation"])
    if re.search(r"quick update|summary|quick", ql):
        return out("Q", ["quick"])
    if re.search(r"fundamental|financial position|fundamentally", ql):
        return out("A", ["dashboard", "fundamental"])
    if re.search(r"technical|chart|bullish|bearish", ql) and len(metrics) <= 1:
        return out("B", ["chart", "ema", "rsi", "candles", "volume", "delivery", "levels", "gaps", "trend"])
    if metrics:
        sections = sorted({k for s, k in metrics if s == "tech"})
        fund = [k for s, k in metrics if s == "fund"]
        if any(s == "tech" for s, _ in metrics):
            sections = ["chart"] + sections
        return out("D", sections + (["metrics"] if fund else []), fund_metrics=fund)
    # nothing specific: a bare symbol -> technical snapshot plus the trade plan (the agent's main use)
    return out("B", ["chart", "ema", "rsi", "candles", "volume", "delivery", "levels", "gaps", "trend"],
               assumed="No scope stated - showing the technical analysis. Ask for 'fundamentals' or 'complete analysis' for more.")
