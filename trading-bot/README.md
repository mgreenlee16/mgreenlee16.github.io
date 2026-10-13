# 15-Minute Opening Range Breakout (ORB) Paper-Trading Bot

A bot that trades the 15-minute opening range breakout on an **Alpaca paper
account** (fake money). It can also **backtest** the same rules on past data so
you can see how the strategy would have done before trusting it.

> The bot is hard-coded to `paper=True`. It cannot place real-money trades.

## The strategy (default settings)

The defaults are the "base strategy" from the ORB videos this bot was built from:

| Rule | Default | Setting in `config.yaml` |
|---|---|---|
| Opening range | High/low (wicks included) of the 9:30–9:45 ET candle | `opening_range_minutes` |
| Entry trigger | A **15-minute candle closes** above the range high. A wick through the range doesn't count | `signal_timeframe_minutes` |
| Entry | Market order at the open of the next candle | – |
| Direction | **Long only**. Shorts lost money in the 5-year S&P 500 test | `direction` (`long` / `short` / `both`) |
| Stop loss | Bottom of the range | `stop_mode` (`opposite` / `midpoint` / `candle`) |
| Profit target | 1.5× the risk (1.5R) | `reward_risk` |
| Late cutoff | No new trades after 11:30 (6–7 candles inside the range = choppy day) | `last_entry_time` |
| End of day | Close everything at 15:55 | `flatten_time` |
| What it trades | SPY and QQQ | `symbols` |
| Size | Risk 1% of the account per trade | `risk_per_trade_pct`, `max_position_pct` |
| Limits | 1 trade per symbol per day, stop after a −3% day | `max_trades_per_day`, `daily_loss_limit_pct` |

Optional filters from the videos (off by default, so you can backtest them on vs. off):

| Filter | Idea | Setting |
|---|---|---|
| Range size | Skip days when the opening range is too tight or too wide | `min_range_pct`, `max_range_pct` |
| Trend | Only go long when the stock is in an uptrend (yesterday's close above its N-day average). This is the fix for fakeouts suggested in the "most traders lose with ORB" video | `trend_filter_days` (e.g. 20) |

Not automated: the discretionary parts, like reading lower highs/lower lows to
exit early, fading the range edges on choppy days, re-entering after a fakeout,
or Fibonacci levels. A trailing stop could be added later.

## One-time setup

### 1. Get a free Alpaca paper account
1. Sign up at <https://alpaca.markets> (no deposit needed for paper trading).
2. In the dashboard, make sure you're on the **Paper** account (top-left switcher).
3. On the right side, under **API Keys**, click **Generate New Keys**.
   Copy the **Key ID** and **Secret Key** (the secret is shown only once).

### 2. Install Python
Install Python 3.10 or newer from <https://www.python.org/downloads/>
(on Windows, tick **"Add Python to PATH"** during install).

### 3. Install the bot
Open a terminal (Mac: *Terminal*; Windows: *PowerShell*) in this `trading-bot` folder:

```bash
python -m venv .venv
# Mac/Linux:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

pip install -r requirements.txt
```

### 4. Add your keys
Copy `.env.example` to a new file named `.env` and paste your paper keys in.
`.env` is ignored by git, so your keys never get uploaded.

### 5. Check everything works
```bash
python run.py check
```
You should see your paper account equity and a count of SPY bars.

## Backtest first

```bash
python run.py backtest --start 2024-01-01 --end 2025-12-31
```

The first run downloads 1-minute data (a few minutes); later runs use the
cached copy in `data/`. You'll get a summary like win rate, profit factor,
max drawdown and average R per trade, broken down by long/short and by
symbol. Every trade is saved to `results/trades.csv` (opens in Excel), so you
can check trades against a chart.

How to read it:
- **Profit factor** above 1.0 means it made money; 1.3+ is respectable after costs.
- **Average R** is profit per trade in units of risk. +0.1R means you made 10% of
  your risk on an average trade.
- Look at **different years separately**. A strategy that only worked in one
  year probably got lucky.
- Avoid tweaking settings until one period looks great. Pick settings on one
  date range, then confirm they also work on a different one.

The backtest is deliberately conservative: it fills you on the next minute's
open plus slippage, and if a single minute touches both your stop and your
target, it counts the stop.

## Compare timeframes and targets (the video's experiment)

```bash
python run.py compare --start 2020-01-01 --end 2025-12-31
```

This reruns the backtest for 1-, 5- and 15-minute entry candles × targets of
1.0R–3.0R, for longs and for shorts (30 runs, about 5–10 minutes), and prints
one table. It's the same experiment as the timeframe video, which found:
15-min worked best at 1.5R, 5-min at 2.0R, 1-min at 2.5R, and shorts lost
money. Your table will show whether that holds on SPY/QQQ after slippage. To
use a different combination, change `signal_timeframe_minutes` and
`reward_risk` in `config.yaml`.

Expect your numbers to differ from the video's. Its returns (like 75% a year)
probably come from a leveraged S&P 500 product with no trading costs. This bot
trades SPY/QQQ shares and charges slippage on every fill.

## Paper trade live

```bash
python run.py live
```

Start it any time before 9:30 ET on a trading day and leave the terminal open.
It will:
1. Wait for the open, then record the 9:30–9:45 range.
2. Check every minute for a finished 15-minute candle (10:00, 10:15, ...) that closed outside the range.
3. Send a **bracket order** (entry + stop + target together), so the stop and
   target live at Alpaca even if your computer goes to sleep.
4. Close everything at 15:55.

Everything it does is printed and saved to `logs/live_YYYY-MM-DD.log`. Watch
your trades in the Alpaca dashboard. Press `Ctrl+C` to stop the bot; any open
trades keep their stop and target orders.

If you restart the bot mid-day, it won't re-trade a stock it already traded.
If it notices a breakout more than 2 minutes late (for example, you started it
at 10:30), it skips that stock for the day rather than chasing.

## Files

| File | What it does |
|---|---|
| `config.yaml` | All strategy settings |
| `orb/strategy.py` | The ORB rules (shared by backtest and live, so they always match) |
| `orb/backtest.py` | Replays the rules on history and scores them |
| `orb/live.py` | Real-time paper trading loop |
| `orb/data.py` | Downloads market data from Alpaca |
| `run.py` | Command-line entry point |
| `tests/` | Checks the rules on made-up data: `python -m pytest` |

## Good to know
- **Data feed:** live trading uses Alpaca's free IEX feed, which covers only
  part of the market's volume, so its candles can differ slightly from your
  charting platform. Backtests use the full-market (SIP) feed.
- **Shorting:** the bot skips shorts on stocks Alpaca marks as not easy to borrow.
- **Going live with real money** later: US accounts under $25k are limited by the
  Pattern Day Trader rule. Paper trade for several weeks first and compare
  results with the backtest.
