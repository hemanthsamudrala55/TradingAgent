"""Portfolio performance and benchmark comparison (Master Instruction Module 3).

Every stock lot is mirrored by a benchmark purchase of the same rupee amount on
the same date (next trading day if the date was a holiday - this is reported).
All series are valued on one common valuation date.

price_fn(symbol, start, end) -> dict(close=Series, splits=Series, dividends=Series)
  close is split-adjusted (Yahoo / Kite convention); split ratios convert the
  user's original quantity, dividends are added to total return when supplied.
bench_fn(bench_cfg, start, end) -> (Series, meta)
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config


@dataclass
class Lot:
    symbol: str
    date: str
    qty: float
    price: float

    @property
    def amount(self) -> float:
        return self.qty * self.price


def _on_or_after(s: pd.Series, d: pd.Timestamp) -> tuple[pd.Timestamp, float]:
    after = s[s.index >= d]
    if after.empty:
        raise LookupError(f"No data on or after {d.date()}")
    return after.index[0], float(after.iloc[0])


def _on_or_before(s: pd.Series, d: pd.Timestamp) -> tuple[pd.Timestamp, float]:
    b = s[s.index <= d]
    return b.index[-1], float(b.iloc[-1])


def _stats(values: pd.Series) -> dict:
    r = values.pct_change().dropna()
    dd = (values / values.cummax() - 1).min()
    return {"volatility_ann_pct": round(float(r.std() * math.sqrt(252) * 100), 2) if len(r) > 5 else None,
            "max_drawdown_pct": round(float(dd * 100), 2) if len(values) else None}


def _cagr(start_v, end_v, days, min_days):
    if days < min_days or start_v <= 0:
        return None
    return round(((end_v / start_v) ** (365.25 / days) - 1) * 100, 2)


def analyse(lots: list[Lot], price_fn, bench_fn, valuation_date: str | None = None,
            benchmarks: list[dict] | None = None, cfg: dict | None = None) -> dict:
    cfg = cfg or config.load()
    pc = cfg["portfolio"]
    benchmarks = benchmarks if benchmarks is not None else pc["benchmarks"]
    start = min(pd.Timestamp(l.date) for l in lots) - pd.Timedelta(days=7)
    end = pd.Timestamp(valuation_date) if valuation_date else pd.Timestamp.today().normalize()

    prices = {s: price_fn(s, start.strftime("%Y-%m-%d"), (end + pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
              for s in {l.symbol for l in lots}}
    bench, unavailable = {}, []
    for b in benchmarks:
        try:
            s, meta = bench_fn(b, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
            bench[b["id"]] = (s.sort_index(), meta)
        except Exception as e:  # noqa: BLE001 - a missing benchmark is reported, never estimated
            unavailable.append({"benchmark": b["name"], "reason": str(e)})

    # one common valuation date: the latest date every series has data for
    last_dates = [p["close"].index.max() for p in prices.values()] + [s.index.max() for s, _ in bench.values()]
    vdate = min(min(last_dates), end)
    adjustments = []

    # ---- each lot and its mirror benchmark purchase ---------------------
    stock_rows, mirror = [], {bid: [] for bid in bench}
    first_buy = {}  # symbol -> first purchase trading day (risk stats run from there)
    for l in lots:
        p = prices[l.symbol]
        d0 = pd.Timestamp(l.date)
        td, _ = _on_or_after(p["close"], d0)
        if td != d0:
            adjustments.append(f"{l.symbol}: {d0.date()} was not a trading day - used {td.date()}")
        splits = p.get("splits", pd.Series(dtype=float))
        factor = float(np.prod(splits[(splits.index > td) & (splits.index <= vdate)].to_numpy())) if len(splits) else 1.0
        divs = p.get("dividends", pd.Series(dtype=float))
        _, cmp_ = _on_or_before(p["close"], vdate)
        qty_now = l.qty * factor
        div_cash = float((divs[(divs.index > td) & (divs.index <= vdate)] * qty_now).sum()) if len(divs) else 0.0
        value = qty_now * cmp_
        pl = value + div_cash - l.amount
        days = (vdate - td).days
        stock_rows.append({"symbol": l.symbol, "buy_date": td.strftime("%Y-%m-%d"), "qty": l.qty, "buy_price": l.price,
                           "investment": round(l.amount, 2), "split_factor": factor, "qty_now": qty_now,
                           "cmp": round(cmp_, 2), "current_value": round(value, 2), "dividends": round(div_cash, 2),
                           "pl": round(pl, 2), "return_pct": round(pl / l.amount * 100, 2), "holding_days": days,
                           "cagr_pct": _cagr(l.amount, value + div_cash, days, pc["cagr_min_days"])})
        first = first_buy.get(l.symbol)
        first_buy[l.symbol] = td if first is None else min(first, td)
        for bid, (s, _) in bench.items():
            bd, bv0 = _on_or_after(s, td)
            _, bv1 = _on_or_before(s, vdate)
            units = l.amount / bv0
            mirror[bid].append({"symbol": l.symbol, "date": bd, "amount": l.amount, "units": units, "value": units * bv1})

    # ---- aggregate per stock -------------------------------------------
    by_stock = {}
    for r in stock_rows:
        a = by_stock.setdefault(r["symbol"], {"symbol": r["symbol"], "investment": 0, "current_value": 0, "dividends": 0, "pl": 0, "lots": 0})
        for k in ("investment", "current_value", "dividends", "pl"):
            a[k] += r[k]
        a["lots"] += 1
    total_inv = sum(a["investment"] for a in by_stock.values())
    total_pl = sum(a["pl"] for a in by_stock.values())
    for a in by_stock.values():
        a["return_pct"] = round(a["pl"] / a["investment"] * 100, 2)
        a["contribution_pct_points"] = round(a["pl"] / total_inv * 100, 2)
        a["weight_pct"] = round(a["investment"] / total_inv * 100, 2)
        c = prices[a["symbol"]]["close"]
        a.update(_stats(c[(c.index >= first_buy[a["symbol"]]) & (c.index <= vdate)]))
        for bid, rows in mirror.items():
            rr = [m for m in rows if m["symbol"] == a["symbol"]]
            bval = sum(m["value"] for m in rr)
            binv = sum(m["amount"] for m in rr)
            a[f"vs_{bid}_pct_points"] = round(a["return_pct"] - (bval / binv - 1) * 100, 2)
        for k in ("investment", "current_value", "dividends", "pl"):
            a[k] = round(a[k], 2)

    stocks = sorted(by_stock.values(), key=lambda x: -x["return_pct"])
    port_ret = total_pl / total_inv * 100

    comp = [{"investment": "Your portfolio" if len(by_stock) > 1 else stocks[0]["symbol"],
             "initial": round(total_inv, 2), "current": round(total_inv + total_pl, 2),
             "pl": round(total_pl, 2), "return_pct": round(port_ret, 2), "source": "price data"}]
    bench_stats = {}
    for bid, (s, meta) in bench.items():
        bv = sum(m["value"] for m in mirror[bid])
        comp.append({"investment": meta["name"], "initial": round(total_inv, 2), "current": round(bv, 2),
                     "pl": round(bv - total_inv, 2), "return_pct": round((bv / total_inv - 1) * 100, 2), "source": meta["source"]})
        first = min(m["date"] for m in mirror[bid])
        bench_stats[meta["name"]] = _stats(s[(s.index >= first) & (s.index <= vdate)])
        for m in mirror[bid]:
            m["date"] = m["date"].strftime("%Y-%m-%d")

    interp = []
    for c in comp[1:]:
        diff = port_ret - c["return_pct"]
        interp.append(f"{comp[0]['investment']} {'outperformed' if diff > 0 else 'underperformed'} {c['investment']} by {abs(diff):.2f} percentage points.")
    if stocks:
        interp.append(f"Best: {stocks[0]['symbol']} ({stocks[0]['return_pct']}%). Worst: {stocks[-1]['symbol']} ({stocks[-1]['return_pct']}%).")
    interp.append("Historical outperformance does not imply future returns.")

    return {"valuation_date": vdate.strftime("%Y-%m-%d"), "lots": stock_rows, "stocks": stocks,
            "total_investment": round(total_inv, 2), "total_value": round(total_inv + total_pl, 2),
            "total_pl": round(total_pl, 2), "portfolio_return_pct": round(port_ret, 2),
            "best": stocks[0]["symbol"] if stocks else None, "worst": stocks[-1]["symbol"] if stocks else None,
            "comparison": comp, "benchmark_risk": bench_stats, "benchmark_unavailable": unavailable,
            "date_adjustments": adjustments, "interpretation": interp,
            "dividends_note": "Dividends included where the price source supplies them (Yahoo does; Kite does not)."}


def what_if(symbol: str, amount: float, months: int, price_fn, bench_fn, cfg=None, valuation_date=None) -> dict:
    """'If I invested Rs X N months ago, what would it be worth today?'"""
    end = pd.Timestamp(valuation_date) if valuation_date else pd.Timestamp.today().normalize()
    d0 = end - pd.DateOffset(months=months)
    p = price_fn(symbol, (d0 - pd.Timedelta(days=7)).strftime("%Y-%m-%d"), (end + pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
    td, px = _on_or_after(p["close"], d0)
    return analyse([Lot(symbol, td.strftime("%Y-%m-%d"), amount / px, px)], lambda *a: p, bench_fn, valuation_date, cfg=cfg)
