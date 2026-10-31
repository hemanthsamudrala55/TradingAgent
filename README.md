# Trading Agent

An NSE stock research and positional-trading agent. Its only instruction set is
[`docs/MASTER_INSTRUCTION.md`](docs/MASTER_INSTRUCTION.md).

**Start with the full guide: [`docs/GUIDE.md`](docs/GUIDE.md)**. It covers setup, every rule, all assumptions, data sources, what has been tested, merging into the existing agent and pushing to GitHub.

Every number the document
does not fix is an assumption and lives in [`config/assumptions.yaml`](config/assumptions.yaml).

## Run

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows   (source .venv/bin/activate on Mac/Linux)
pip install -r requirements.txt
copy .env.example .env          # add Kite keys for live data (optional)
python -m web.app               # open http://127.0.0.1:5000
python -m pytest                # tests
```

## Simple view

The main page has three plain-language screens:

| Screen | What it does |
|---|---|
| Stocks | Search any NSE stock. Candles and volume by Hour, Day, Month, Quarter, Half-year or Year. |
| Robot | Set the mode, money, loss limit and stocks. Practice and Ask me first work. Automatic is locked. |
| Activity | Every decision and its reason, with Approve or Skip for suggestions. |

The robot only uses pretend money. It has no code that sends orders, even for approved trades. It runs while the dashboard is open and judges each stock once per finished daily candle.

## Advanced view (`/advanced`)

| Tab | What it does |
|---|---|
| Analyze | Ask in plain language ("positional trading", "support and resistance", "fundamentals", "ROCE ROE debt-to-equity", "compare TCS vs INFY"). Shows only what you asked for (Master Instruction modes A-F). Upload your own chart CSV to check levels against it. |
| Setups | Scans the watchlist (`config/watchlist.yaml`) and ranks ENTER / WAIT / AVOID CHASING / AVOID. |
| Simulation | Day-by-day back-test of the positional rules over any date range. |
| Paper | The same engine run forward from a paper start date to the latest candle. No orders. |
| Live | Zerodha holdings, positions and a HOLD / EXIT check against each GTT stop. Read-only. |
| Portfolio vs benchmark | Module 3: your lots against Nifty Smallcap 250 TRI, Nifty Smallcap 100 TRI and Motilal Oswal Small Cap Fund (Direct Growth), with the same amounts on the same dates. |
| Assumptions / Master Instruction | The two documents that drive everything. |

## Data sources

| Data | Source | Notes |
|---|---|---|
| Daily candles | Zerodha Kite (when connected), otherwise Yahoo Finance, or your uploaded CSV | |
| Delivery % | NSE `sec_bhavdata_full` daily files | Kite does not provide it |
| Fundamentals | Screener.in public company page | Login-only ratios (ROIC, pledge, industry P/E) show as **Unavailable** |
| Nifty TRI | niftyindices.com | or drop a CSV at `state/benchmarks/<id>.csv` |
| Fund NAV | AMFI via mfapi.in | scheme matched by name and plan words |

Missing values are always shown as Unavailable. They are never estimated.

## How support and resistance are found

1. Swing highs and lows: a candle whose high (or low) is the extreme of 5 candles on each side, over the last 250 sessions.
2. Swings within max(0.6 × ATR, 0.75 % of price) of each other merge into one zone.
3. Zones below the close are support and zones above are resistance. The nearest one is *immediate*. The nearest with 3+ touches (a weekly swing counts as one more) is *strong* / *major*.
4. Every zone lists the dates and prices of its swing points so you can find each touch on your chart.

## Layout

```
master_agent/   indicators, levels, candles, technical, positional, fundamentals, portfolio, simulate, router
master_agent/data/   kite, yahoo, nse_delivery, benchmarks, CSV loader
web/            Flask server + single-page dashboard
config/         assumptions.yaml, watchlist.yaml
docs/           MASTER_INSTRUCTION.md
tests/
```
