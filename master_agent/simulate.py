"""Day-by-day simulation of the Master Instruction positional framework.

No look-ahead: the decision on day t uses candles up to and including t, and
orders fill at day t+1's open. Stops, T1 and T2 are checked against each
day's high / low; gap-throughs fill at the open. Paper trading is this same
simulation started on the paper start date and run up to the latest candle.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict

import pandas as pd

from . import config, levels as lv, positional, technical as tech


@dataclass
class Position:
    symbol: str
    entry_date: str
    entry: float
    qty: int
    stop: float
    t1: float
    t2: float
    setup: str
    initial_stop: float
    orig_qty: int = 0
    invalidate_below: str = "ema63"
    t1_done: bool = False
    exit_next_open: str | None = None
    realised: float = 0.0
    charges: float = 0.0


@dataclass
class Book:
    cash: float
    positions: dict = field(default_factory=dict)
    trades: list = field(default_factory=list)
    equity: list = field(default_factory=list)


def _cost(value: float, sell: bool, s: dict) -> float:
    return value * s["charges_pct_per_side"] / 100 + (s["dp_charge_per_sell"] if sell else 0)


def run(data: dict[str, pd.DataFrame], start: str, end: str | None = None, cfg: dict | None = None,
        capital: float | None = None, benchmark: pd.Series | None = None) -> dict:
    cfg = cfg or config.load()
    s = cfg["simulation"]
    book = Book(cash=float(capital or s["starting_capital"]))
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end) if end else max(df.index.max() for df in data.values())
    prepared = {sym: tech.prepare(df, cfg) for sym, df in data.items()}
    days = sorted(set().union(*[df.index[(df.index >= start_ts) & (df.index <= end_ts)] for df in data.values()]))
    lv_prev: dict[str, dict] = {}
    pending: dict[str, dict] = {}
    slip = s["slippage_pct"] / 100

    def close_out(pos: Position, qty: int, price: float, day, reason: str):
        value = qty * price
        ch = _cost(value, True, s)
        book.cash += value - ch
        pos.realised += qty * (price - pos.entry)
        pos.charges += ch
        pos.qty -= qty
        if pos.qty == 0:
            del book.positions[pos.symbol]
            net = pos.realised - pos.charges
            book.trades.append({**{k: v for k, v in asdict(pos).items() if k not in ("exit_next_open",)},
                                "exit_date": day.strftime("%Y-%m-%d"), "exit_price": round(price, 2), "exit_reason": reason,
                                "qty": pos.orig_qty, "net_pl": round(float(net), 2),
                                "r_multiple": round(float(pos.realised / ((pos.entry - pos.initial_stop) * pos.orig_qty)), 2)})

    for day in days:
        # 1) fills at the open: queued exits, then queued entries
        for sym, pos in list(book.positions.items()):
            df = data[sym]
            if day not in df.index:
                continue
            bar = df.loc[day]
            if pos.exit_next_open:
                close_out(pos, pos.qty, bar.open * (1 - slip), day, pos.exit_next_open)
                continue
            # 2) stop / targets during the day (stop first: conservative)
            if bar.open <= pos.stop:
                close_out(pos, pos.qty, bar.open * (1 - slip), day, "stop (gap below)")
                continue
            if bar.low <= pos.stop:
                close_out(pos, pos.qty, pos.stop * (1 - slip), day, "stop" if not pos.t1_done else "break-even stop after T1")
                continue
            if not pos.t1_done and bar.high >= pos.t1:
                q = max(1, int(pos.qty * s["t1_exit_fraction"])) if pos.qty > 1 else pos.qty
                fill = max(bar.open, pos.t1)
                pos.t1_done = True
                pos.stop = max(pos.stop, pos.entry)
                close_out(pos, q, fill, day, "T1")
                if sym not in book.positions:
                    continue
            if pos.t1_done and bar.high >= pos.t2:
                close_out(pos, pos.qty, max(bar.open, pos.t2), day, "T2")

        for sym, order in list(pending.items()):
            df = data[sym]
            if day not in df.index or sym in book.positions:
                pending.pop(sym)
                continue
            bar = df.loc[day]
            px = bar.open * (1 + slip)
            pending.pop(sym)
            if px <= order["stop"] or (px - order["stop"]) / px * 100 > cfg["positional"]["max_stop_pct"] or px >= order["t1"]:
                continue                       # gapped through the plan - skip, do not chase
            equity = book.cash + sum(p.qty * data[p.symbol]["close"].asof(day) for p in book.positions.values())
            risk_cash = equity * s["risk_per_trade_pct"] / 100
            qty = math.floor(min(risk_cash / (px - order["stop"]), equity * s["max_position_pct"] / 100 / px,
                                 (book.cash - 20) / px))
            if qty < 1:
                continue
            ch = _cost(qty * px, False, s)
            book.cash -= qty * px + ch
            book.positions[sym] = Position(sym, day.strftime("%Y-%m-%d"), round(float(px), 2), qty, order["stop"], order["t1"],
                                           order["t2"], order["setup"], order["stop"], orig_qty=qty,
                                           invalidate_below=order["invalidate_below"], charges=float(ch))

        # 3) end-of-day decisions
        signals = []
        for sym, df in data.items():
            if day not in df.index:
                continue
            i = df.index.get_loc(day)
            if i < 60:
                continue
            cut = df.iloc[:i + 1]
            today_lv = lv.find_levels(cut, cfg)
            d = prepared[sym].iloc[:i + 1]
            pos = book.positions.get(sym)
            if pos:
                res = positional.evaluate(d, today_lv, lv_prev.get(sym), cfg,
                                          position={"stop": pos.stop, "invalidate_below": pos.invalidate_below})
                if res["verdict"] == positional.EXIT and not pos.exit_next_open:
                    pos.exit_next_open = "invalidated: " + "; ".join(res["invalidated_by"])
            elif len(book.positions) < s["max_open_positions"]:
                res = positional.evaluate(d, today_lv, lv_prev.get(sym), cfg)
                if res["verdict"] == positional.ENTER and res["plan"]:
                    pl = res["plan"]
                    signals.append((pl["rr_t1"] or 0, sym, {"stop": pl["stop"], "t1": pl["t1"]["price"], "t2": pl["t2"]["price"], "setup": pl["type"],
                                                         "invalidate_below": res["invalidate_below"]}))
            lv_prev[sym] = today_lv
        slots = s["max_open_positions"] - len(book.positions)
        for _, sym, order in sorted(signals, reverse=True)[:max(0, slots)]:
            pending[sym] = order

        eq = book.cash + sum(p.qty * data[p.symbol]["close"].asof(day) for p in book.positions.values())
        book.equity.append({"date": day.strftime("%Y-%m-%d"), "equity": round(eq, 2)})

    return summarise(book, data, float(capital or s["starting_capital"]), benchmark)


def summarise(book: Book, data, capital: float, benchmark: pd.Series | None) -> dict:
    eq = pd.Series([e["equity"] for e in book.equity], index=pd.to_datetime([e["date"] for e in book.equity])) if book.equity else pd.Series(dtype=float)
    trades = book.trades
    wins = [t for t in trades if t["net_pl"] > 0]
    out = {
        "capital": capital,
        "final_equity": round(float(eq.iloc[-1]), 2) if len(eq) else capital,
        "return_pct": round((float(eq.iloc[-1]) / capital - 1) * 100, 2) if len(eq) else 0.0,
        "max_drawdown_pct": round(float((eq / eq.cummax() - 1).min() * 100), 2) if len(eq) else 0.0,
        "trades": len(trades), "win_rate_pct": round(len(wins) / len(trades) * 100, 1) if trades else None,
        "avg_r": round(float(sum(t["r_multiple"] for t in trades) / len(trades)), 2) if trades else None,
        "charges": round(float(sum(t["charges"] for t in trades) + sum(p.charges for p in book.positions.values())), 2),
        "cash": round(float(book.cash), 2),
        "equity_curve": book.equity,
        "closed_trades": trades,
        "open_positions": [{**asdict(p), "last": round(float(data[p.symbol]["close"].iloc[-1]), 2),
                            "unrealised": round(p.qty * (float(data[p.symbol]["close"].iloc[-1]) - p.entry), 2)}
                           for p in book.positions.values()],
    }
    if benchmark is not None and len(eq):
        b = benchmark.reindex(eq.index, method="ffill").dropna()
        if len(b):
            out["benchmark_curve"] = [{"date": d.strftime("%Y-%m-%d"), "equity": round(capital * v / b.iloc[0], 2)} for d, v in b.items()]
            out["benchmark_return_pct"] = round((b.iloc[-1] / b.iloc[0] - 1) * 100, 2)
    return out
