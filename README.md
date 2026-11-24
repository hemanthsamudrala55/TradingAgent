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

The robot uses pretend money unless you switch on real orders (Robot screen, section 6). It runs while the dashboard is open and judges each stock once per finished daily candle. Every buy must pass the safety limits in section 5.

### Real orders with Zerodha

Off by default. A real order is sent only when all of these hold:

1. Your own Kite Connect app keys are in `.env` (a paid Zerodha plan) and you are logged in with **Connect Zerodha**. The key-free connection is read-only and is never used for orders.
2. The robot is in **Ask me first** mode and you typed `REAL MONEY` to switch real orders on.
3. The suggestion you approve is exactly the one shown, still passes every safety limit, and you typed its confirmation, for example `BUY 10 INFY`.

The order is a delivery (CNC) **limit** buy at the suggested price, valid for the day; outside market hours it goes in as an after-market order. Each approval sends one order, which is never retried. Once it fills, the robot places a GTT OCO at Zerodha: a stop-loss sell and a target sell. If Zerodha refuses the stop-loss, the Activity screen says so in red and the robot tries again on each check, so set one in Kite yourself.

Since 1 April 2026 Zerodha accepts API orders only from a static IP address registered on your Kite Connect app. Register yours first, or orders will be refused.

Stopping the robot halts new decisions and approvals. It does not cancel orders or GTTs already at Zerodha. Real trade sell prices are not read back, so for the daily loss limit a closed real trade counts as a full loss until you check Kite.

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
