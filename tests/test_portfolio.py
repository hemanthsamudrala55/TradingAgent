import pandas as pd
import pytest

from master_agent import portfolio
from master_agent.portfolio import Lot


def _series(vals, start="2026-01-01"):
    return pd.Series(vals, index=pd.bdate_range(start, periods=len(vals)), dtype=float)


def price_fn(sym, start, end):
    return {"AAA": {"close": _series([100] * 5 + [110] * 5 + [120] * 10)},
            "BBB": {"close": _series([50] * 10 + [40] * 10)}}[sym]


def bench_fn(b, start, end):
    return _series([1000] * 10 + [1050] * 10), {"source": "test", "name": b["name"]}


BENCH = [{"id": "x", "name": "Test TRI", "kind": "nifty_tri", "index_name": "X"}]


def test_single_stock_matches_formula_and_benchmark_uses_same_amount_and_date():
    r = portfolio.analyse([Lot("AAA", "2026-01-01", 10, 100)], price_fn, bench_fn, benchmarks=BENCH)
    s = r["stocks"][0]
    assert s["investment"] == 1000 and s["current_value"] == 1200 and s["pl"] == 200 and s["return_pct"] == 20
    b = r["comparison"][1]
    assert b["initial"] == 1000 and b["current"] == 1050 and b["return_pct"] == 5
    assert s["vs_x_pct_points"] == 15


def test_weekend_purchase_uses_next_trading_day():
    r = portfolio.analyse([Lot("AAA", "2026-01-03", 10, 100)], price_fn, bench_fn, benchmarks=BENCH)  # Saturday
    assert r["lots"][0]["buy_date"] == "2026-01-05"
    assert r["date_adjustments"]


def test_portfolio_weights_follow_actual_amounts():
    r = portfolio.analyse([Lot("AAA", "2026-01-01", 10, 100), Lot("BBB", "2026-01-01", 60, 50)], price_fn, bench_fn,
                          benchmarks=BENCH)
    w = {s["symbol"]: s["weight_pct"] for s in r["stocks"]}
    assert w == {"AAA": 25.0, "BBB": 75.0}
    assert r["total_pl"] == 200 - 600
    assert r["best"] == "AAA" and r["worst"] == "BBB"
    assert pytest.approx(sum(s["contribution_pct_points"] for s in r["stocks"]), abs=0.02) == r["portfolio_return_pct"]


def test_split_adjusts_original_quantity():
    def pf(sym, start, end):
        c = _series([50] * 20)
        return {"close": c, "splits": pd.Series([2.0], index=[c.index[5]])}
    r = portfolio.analyse([Lot("AAA", "2026-01-01", 10, 100)], pf, bench_fn, benchmarks=BENCH)
    assert r["lots"][0]["qty_now"] == 20 and r["stocks"][0]["pl"] == 0


def test_missing_benchmark_reported_not_estimated():
    def bad(b, s, e):
        raise LookupError("site down")
    r = portfolio.analyse([Lot("AAA", "2026-01-01", 10, 100)], price_fn, bad, benchmarks=BENCH)
    assert r["benchmark_unavailable"][0]["reason"] == "site down"
    assert len(r["comparison"]) == 1
