"""Dashboard server.  Run:  python -m web.app   then open http://127.0.0.1:5000"""
from __future__ import annotations

import os
import re
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from flask import Flask, jsonify, redirect, render_template, request

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from master_agent import config, frames, fundamentals, levels, portfolio, positional, robot, router, simulate, technical  # noqa: E402
from master_agent import data as mdata  # noqa: E402
from master_agent.data import benchmarks, kite, nse_delivery, yahoo  # noqa: E402


def _load_env():
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_env()
app = Flask(__name__)
_cache: dict = {}
_uploads: dict[str, pd.DataFrame] = {}


def _clean(o):
    """Make numpy / pandas values JSON safe."""
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items() if not str(k).startswith("_")}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, pd.Timestamp):
        return o.strftime("%Y-%m-%d")
    return o


def ok(payload):
    return jsonify(_clean(payload))


def err(msg, code=400):
    return jsonify({"error": str(msg)}), code


def source_name(src: str) -> str:
    return {"kite": kite.SOURCE, "yahoo": yahoo.SOURCE, "upload": "Uploaded chart data (CSV)"}[src]


def daily(symbol: str, src: str, start: str, end: str | None = None) -> pd.DataFrame:
    if src == "upload":
        if symbol not in _uploads:
            raise LookupError(f"No uploaded chart for {symbol}")
        return _uploads[symbol]
    key = (symbol, src, start, end)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    fn = kite.daily if src == "kite" else yahoo.daily
    df = fn(symbol, start, end)
    _cache[key] = (time.time(), df)
    return df


def default_source() -> str:
    return "kite" if kite.connected().get("connected") else "yahoo"


def candles_payload(df: pd.DataFrame, cfg) -> dict:
    d = technical.prepare(df, cfg).iloc[-400:]
    t = [i.strftime("%Y-%m-%d") for i in d.index]
    line = lambda c: [{"time": a, "value": round(float(v), 2)} for a, v in zip(t, d[c]) if not pd.isna(v)]
    return {"candles": [{"time": a, "open": r.open, "high": r.high, "low": r.low, "close": r.close} for a, r in zip(t, d.itertuples())],
            "volume": [{"time": a, "value": float(r.volume), "up": bool(r.close >= r.open)} for a, r in zip(t, d.itertuples())],
            "ema21": line("ema21"), "ema63": line("ema63"), "ema200": line("ema200"), "rsi": line("rsi")}


@app.get("/")
def simple():
    return render_template("simple.html")


@app.get("/advanced")
def index():
    return render_template("index.html")


@app.get("/api/status")
def status():
    return ok({"kite": kite.connected(), "uploads": sorted(_uploads), "default_source": default_source(),
               "watchlist": yaml.safe_load((ROOT / "config" / "watchlist.yaml").read_text())["symbols"]})


@app.get("/api/assumptions")
def assumptions():
    return ok({"text": config.raw_text()})


@app.get("/api/instructions")
def instructions():
    return ok({"text": (ROOT / "docs" / "MASTER_INSTRUCTION.md").read_text(encoding="utf-8")})


@app.post("/api/upload-chart")
def upload_chart():
    f = request.files.get("file")
    sym = (request.form.get("symbol") or "").strip().upper()
    if not f or not sym:
        return err("Send a CSV file and a symbol")
    try:
        df = mdata.read_csv(f.read())
    except Exception as e:  # noqa: BLE001
        return err(f"Could not read chart data: {e}")
    _uploads[sym] = df
    return ok({"symbol": sym, "candles": len(df), "from": df.index[0], "to": df.index[-1]})


@app.post("/api/analyze")
def analyze():
    b = request.get_json(force=True)
    cfg = config.load()
    sym = (b.get("symbol") or "").strip().upper()
    r = router.route(b.get("query") or "", sym or None)
    sym = sym or (r["symbols"][0] if r["symbols"] else "")
    if not sym:
        return err("Which stock? Enter a symbol or name it in the question.")
    src = b.get("source") or default_source()
    out = {"route": r, "symbol": sym, "source": source_name(src)}
    needs_tech = any(s in r["sections"] for s in ("chart", "ema", "rsi", "candles", "volume", "delivery", "levels",
                                                   "gaps", "trend", "positional", "technical", "quick"))
    if needs_tech:
        try:
            start = (pd.Timestamp.today() - pd.DateOffset(years=3)).strftime("%Y-%m-%d")
            df = daily(sym, src, start)
            if "delivery" in r["sections"] or r["mode"] in ("B", "C"):
                df = nse_delivery.attach(df, sym)
            out["technical"] = technical.analyse(df, cfg)
            out["plan"] = positional.plan(df, cfg)
            out["chart"] = candles_payload(df, cfg)
            out["data_range"] = [df.index[0], df.index[-1]]
        except Exception as e:  # noqa: BLE001
            out["technical_error"] = f"Price data unavailable from {source_name(src)}: {e}"
    if any(s in r["sections"] for s in ("dashboard", "fundamental", "metrics", "valuation", "quick", "conclusion")):
        try:
            out["fundamentals"] = fundamentals.dashboard(fundamentals.fetch_screener(sym))
        except Exception as e:  # noqa: BLE001
            out["fundamentals_error"] = f"Screener.in data unavailable: {e}"
    return ok(out)


@app.post("/api/compare")
def compare():
    b = request.get_json(force=True)
    syms = [s.strip().upper() for s in b.get("symbols", []) if s.strip()]
    src = b.get("source") or default_source()
    rows = []
    for s in syms:
        row = {"symbol": s}
        try:
            row["fundamentals"] = fundamentals.dashboard(fundamentals.fetch_screener(s))
        except Exception as e:  # noqa: BLE001
            row["fundamentals_error"] = str(e)
        try:
            df = daily(s, src, (pd.Timestamp.today() - pd.DateOffset(years=2)).strftime("%Y-%m-%d"))
            row["plan"] = positional.plan(df)
            row["ema_structure"] = technical.analyse(df)["ema"].get("structure")
        except Exception as e:  # noqa: BLE001
            row["technical_error"] = str(e)
        rows.append(row)
    return ok({"rows": rows})


@app.post("/api/dcf")
def dcf():
    b = request.get_json(force=True)
    base = {k: float(b[k]) for k in ("fcf_base", "shares", "growth_pct", "discount_pct", "terminal_pct")}
    base["years"] = int(b.get("years", 5))
    base["net_debt"] = float(b.get("net_debt", 0))
    return ok({"result": fundamentals.dcf(**base), "sensitivity": fundamentals.dcf_sensitivity(base)})


def _universe(b) -> list[str]:
    syms = b.get("symbols") or yaml.safe_load((ROOT / "config" / "watchlist.yaml").read_text())["symbols"]
    return [s.strip().upper() for s in syms if s.strip()]


def _run_sim(b, end=None):
    cfg = config.load()
    src = b.get("source") or default_source()
    start = b["start"]
    warm = (pd.Timestamp(start) - pd.DateOffset(days=450)).strftime("%Y-%m-%d")
    data, skipped = {}, []
    for s in _universe(b):
        try:
            data[s] = daily(s, src, warm, end)
        except Exception as e:  # noqa: BLE001
            skipped.append({"symbol": s, "reason": str(e)})
    if not data:
        raise LookupError("No price data for any symbol: " + "; ".join(x["reason"] for x in skipped))
    bench = None
    try:
        bench = daily("^NSEI", "yahoo", warm, end)["close"] if src != "kite" else kite.daily("NIFTY 50", warm, end)["close"]
    except Exception:  # noqa: BLE001 - benchmark curve is optional
        pass
    res = simulate.run(data, start, end, cfg, float(b.get("capital") or cfg["simulation"]["starting_capital"]), bench)
    res.update(skipped=skipped, source=source_name(src), symbols=sorted(data), benchmark_name="Nifty 50 (price index)")
    return res


@app.post("/api/simulate")
def api_simulate():
    b = request.get_json(force=True)
    try:
        return ok(_run_sim(b, b.get("end") or None))
    except Exception as e:  # noqa: BLE001
        return err(e)


@app.post("/api/paper")
def api_paper():
    """Paper trading = the same engine from the paper start date to the latest candle."""
    b = request.get_json(force=True)
    try:
        res = _run_sim(b)
        res["note"] = "Paper portfolio replayed from the start date to the latest candle. No orders are sent."
        return ok(res)
    except Exception as e:  # noqa: BLE001
        return err(e)


@app.get("/kite/login")
def kite_login():
    try:
        return redirect(kite.login_url())
    except Exception as e:  # noqa: BLE001
        return err(e)


@app.get("/kite/callback")
def kite_callback():
    tok = request.args.get("request_token")
    if not tok:
        return err("Missing request_token")
    try:
        kite.complete_login(tok)
    except Exception as e:  # noqa: BLE001
        return err(e)
    return redirect("/advanced#live")


@app.get("/api/live")
def live():
    """Read-only view of the Zerodha account plus a HOLD / EXIT check for each holding."""
    st = kite.connected()
    if not st.get("connected"):
        return ok({"connected": False, "reason": st.get("reason")})
    cfg = config.load()
    start = (pd.Timestamp.today() - pd.DateOffset(years=2)).strftime("%Y-%m-%d")
    gtt_stops = {}
    try:
        for g in kite.gtts():
            if g.get("status") == "active":
                sym = g["condition"]["tradingsymbol"]
                gtt_stops[sym] = min(g["condition"]["trigger_values"])
    except Exception:  # noqa: BLE001
        pass
    rows = []
    for h in kite.holdings():
        q = h.get("quantity", 0) + h.get("t1_quantity", 0)
        if q <= 0:
            continue
        sym = h["tradingsymbol"]
        row = {"symbol": sym, "qty": q, "avg": h["average_price"], "ltp": h["last_price"],
               "pl": round((h["last_price"] - h["average_price"]) * q, 2),
               "pl_pct": round((h["last_price"] / h["average_price"] - 1) * 100, 2) if h["average_price"] else None,
               "gtt_stop": gtt_stops.get(sym)}
        try:
            df = daily(sym, "kite", start)
            fresh = positional.plan(df, cfg)
            stop = gtt_stops.get(sym) or (fresh.get("pullback_plan") or {}).get("stop")
            row["check"] = positional.plan(df, cfg, position={"stop": stop}) if stop else None
            row["levels"] = fresh
        except Exception as e:  # noqa: BLE001
            row["error"] = str(e)
        rows.append(row)
    return ok({"connected": True, "user": st.get("user"), "holdings": rows, "positions": kite.positions(),
               "note": "Read-only. The dashboard never places or modifies orders."})


@app.post("/api/scan")
def scan():
    b = request.get_json(force=True)
    src = b.get("source") or default_source()
    start = (pd.Timestamp.today() - pd.DateOffset(years=2)).strftime("%Y-%m-%d")
    rows = []
    for s in _universe(b):
        try:
            p = positional.plan(daily(s, src, start))
            rows.append({"symbol": s, "verdict": p["verdict"], "close": p["close"], "trend": p.get("trend"),
                         "rsi": p.get("rsi"), "plan": p.get("plan"), "reasons": p.get("reasons") or [p.get("reason")]})
        except Exception as e:  # noqa: BLE001
            rows.append({"symbol": s, "error": str(e)})
    order = {positional.ENTER: 0, positional.WAIT: 1, positional.CHASE: 2, positional.AVOID: 3}
    rows.sort(key=lambda r: order.get(r.get("verdict"), 9))
    return ok({"rows": rows, "source": source_name(src)})


def _price_fn(src):
    def fn(sym, start, end):
        if src == "yahoo":
            import yfinance as yf
            t = yf.Ticker(f"{sym}.NS")
            h = t.history(start=start, end=end, auto_adjust=False)
            if h.empty:
                raise LookupError(f"No Yahoo data for {sym}")
            idx = h.index.tz_localize(None).normalize()
            sp = h["Stock Splits"].replace(0, np.nan).dropna()
            dv = h["Dividends"].replace(0, np.nan).dropna()
            return {"close": pd.Series(h["Close"].values, idx),
                    "splits": pd.Series(sp.values, sp.index.tz_localize(None).normalize()),
                    "dividends": pd.Series(dv.values, dv.index.tz_localize(None).normalize())}
        return {"close": daily(sym, src, start, end)["close"]}
    return fn


@app.post("/api/portfolio")
def api_portfolio():
    b = request.get_json(force=True)
    src = b.get("source") or "yahoo"
    try:
        if b.get("what_if"):
            w = b["what_if"]
            res = portfolio.what_if(w["symbol"].upper(), float(w["amount"]), int(w["months"]), _price_fn(src),
                                    benchmarks.series, valuation_date=b.get("valuation_date") or None)
        else:
            lots = [portfolio.Lot(l["symbol"].strip().upper(), l["date"], float(l["qty"]), float(l["price"]))
                    for l in b["lots"] if l.get("symbol")]
            if not lots:
                return err("Add at least one holding")
            res = portfolio.analyse(lots, _price_fn(src), benchmarks.series, b.get("valuation_date") or None)
        res["price_source"] = source_name(src) if src != "yahoo" else "Yahoo Finance (close, splits, dividends)"
        return ok(res)
    except Exception as e:  # noqa: BLE001
        return err(e)


@app.get("/api/holdings-as-lots")
def holdings_as_lots():
    """Prefill the portfolio form from Zerodha holdings (purchase dates must be entered by the user)."""
    if not kite.connected().get("connected"):
        return err("Zerodha not connected")
    return ok({"lots": [{"symbol": h["tradingsymbol"], "qty": h["quantity"] + h.get("t1_quantity", 0),
                         "price": h["average_price"], "date": ""} for h in kite.holdings()]})


def _prices(sym: str, fetch) -> tuple[pd.DataFrame, str, str | None]:
    """Zerodha when connected, Yahoo otherwise or if Zerodha fails. Returns (frame, source name, note)."""
    src = default_source()
    if src == "kite":
        try:
            return fetch(sym, "kite"), source_name("kite"), None
        except Exception as e:  # noqa: BLE001
            return fetch(sym, "yahoo"), source_name("yahoo"), f"Zerodha could not supply this ({e}), so these are Yahoo prices."
    return fetch(sym, "yahoo"), source_name("yahoo"), None


def _history(sym: str, src: str) -> pd.DataFrame:
    return daily(sym, src, "2000-01-01")


def _hourly(sym: str, src: str) -> pd.DataFrame:
    key = (sym, src, "hourly")
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    df = (kite if src == "kite" else yahoo).hourly(sym)
    _cache[key] = (time.time(), df)
    return df


@app.get("/api/chart")
def api_chart():
    sym, frame = request.args.get("symbol", "").strip().upper(), request.args.get("frame", "Day")
    if not re.fullmatch(r"[A-Z0-9&\-.]{1,30}", sym):
        return err("Enter a stock symbol, like TCS")
    if frame not in frames.FRAMES:
        return err("Unknown candle size")
    try:
        hist, source, note = _prices(sym, _history)
        rows = _hourly(sym, "kite" if source == kite.SOURCE else "yahoo") if frame == "Hour" else frames.resample(hist, frame)
    except LookupError:
        return err(f"No prices found for {sym}. Check the name and try again.", 404)
    except Exception as e:  # noqa: BLE001
        return err(f"Could not load prices for {sym}: {e}", 502)
    cfg = config.load()
    zones = levels.find_levels(hist, cfg)
    return ok({"symbol": sym, "frame": frame, "candles": frames.payload(rows, frame), "source": source, "note": note,
               "view": robot.plain_view(positional.plan(hist, cfg)),
               "floor": (zones.get("immediate_support") or {}).get("level"),
               "ceiling": (zones.get("immediate_resistance") or {}).get("level")})


@app.get("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return ok({"results": []})
    try:
        import yfinance as yf
        quotes = yf.Search(q, max_results=10, news_count=0).quotes
    except Exception:  # noqa: BLE001 - suggestions are optional, the typed symbol still works
        return ok({"results": []})
    return ok({"results": [{"symbol": x["symbol"][:-3], "name": x.get("longname") or x.get("shortname") or ""}
                           for x in quotes if str(x.get("symbol", "")).endswith(".NS")]})


def _robot_daily(sym: str) -> pd.DataFrame:
    start = (pd.Timestamp.today() - pd.DateOffset(years=3)).strftime("%Y-%m-%d")
    return _prices(sym, lambda s, src: daily(s, src, start))[0]


@app.get("/api/robot")
def api_robot():
    return ok(robot.load())


@app.post("/api/robot/settings")
def api_robot_settings():
    try:
        return ok(robot.update_settings(request.get_json(force=True)))
    except (TypeError, ValueError) as e:
        return err(e)


@app.post("/api/robot/check")
def api_robot_check():
    res = robot.check(_robot_daily)
    return ok({**res["state"], "errors": res["errors"]})


@app.post("/api/robot/pending/<int:pending_id>")
def api_robot_answer(pending_id: int):
    try:
        return ok(robot.answer(pending_id, bool(request.get_json(force=True).get("approve"))))
    except LookupError as e:
        return err(e, 404)


def _robot_loop():
    """While the dashboard is open, check every 15 minutes. Each stock acts once per finished candle."""
    while True:
        try:
            robot.check(_robot_daily)
        except Exception as e:  # noqa: BLE001 - keep the loop alive
            print("Robot check failed:", e, file=sys.stderr)
        time.sleep(900)


if __name__ == "__main__":
    threading.Thread(target=_robot_loop, daemon=True).start()
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=False)
