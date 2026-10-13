"""Command-line entry point.

    python run.py check                                   # test your API keys
    python run.py backtest --start 2025-01-01 --end 2025-12-31
    python run.py compare --start 2020-01-01 --end 2025-12-31   # 1/5/15-min x targets
    python run.py live                                    # paper trade in real time
"""
import argparse
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

from orb.config import load_config


def cmd_check(cfg):
    from alpaca.trading.client import TradingClient

    from orb.data import NY, api_keys, fetch_minute_bars, make_data_client

    trading = TradingClient(*api_keys(), paper=True)
    acct = trading.get_account()
    clock = trading.get_clock()
    print(f"Paper account status: {acct.status}")
    print(f"Equity: ${float(acct.equity):,.2f}   Buying power: ${float(acct.buying_power):,.2f}")
    print(f"Market open now: {clock.is_open}   Next open: {clock.next_open.astimezone(NY)}")
    end = datetime.now(NY) - timedelta(minutes=20)
    bars = fetch_minute_bars(make_data_client(), ["SPY"], end - timedelta(days=5), end,
                             cfg.live_data_feed)
    spy = bars.get("SPY")
    print(f"Market data OK: {0 if spy is None else len(spy)} SPY 1-minute bars in the last 5 days")


def _load_history(cfg, start, end):
    import pandas as pd

    from orb.backtest import split_by_day
    from orb.data import NY, fetch_daily_closes, load_backtest_bars, make_data_client

    client = make_data_client()
    bars = load_backtest_bars(client, cfg.symbols, start, end, cfg.backtest_data_feed)
    daily = None
    if cfg.trend_filter_days > 0:
        # Extra history before `start` so the moving average is ready on day one.
        warmup_start = pd.Timestamp(start, tz=NY) - pd.Timedelta(days=cfg.trend_filter_days * 2 + 10)
        daily = fetch_daily_closes(client, cfg.symbols, warmup_start.to_pydatetime(),
                                   (pd.Timestamp(end, tz=NY) + pd.Timedelta(days=1)).to_pydatetime(),
                                   cfg.backtest_data_feed)
    return split_by_day(bars), daily


def cmd_backtest(cfg, start, end):
    from orb.backtest import run_backtest, summarize

    days, daily = _load_history(cfg, start, end)
    trades, equity = run_backtest(cfg, days, daily)
    print(summarize(trades, equity, cfg))
    if not trades.empty:
        Path("results").mkdir(exist_ok=True)
        trades.to_csv("results/trades.csv", index=False)
        equity.to_csv("results/equity.csv", index_label="date")
        print("\nEvery trade saved to results/trades.csv, daily equity to results/equity.csv")


def cmd_compare(cfg, start, end):
    import pandas as pd

    from orb.backtest import compare

    days, daily = _load_history(cfg, start, end)
    print("Running every combination (this takes a few minutes)...")
    table = compare(cfg, days, daily)
    Path("results").mkdir(exist_ok=True)
    table.to_csv("results/compare.csv", index=False)
    with pd.option_context("display.width", 120):
        print(table.round(2).to_string(index=False))
    print("\nSaved to results/compare.csv")


def cmd_live(cfg):
    from orb.live import LiveTrader, setup_logging

    setup_logging()
    try:
        LiveTrader(cfg).run()
    except KeyboardInterrupt:
        print("\nStopped. Any open positions still have their stop and target orders in Alpaca.")


def main():
    parser = argparse.ArgumentParser(description="15-minute Opening Range Breakout bot")
    parser.add_argument("--config", default="config.yaml")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="verify API keys and data access")
    bt = sub.add_parser("backtest", help="test the strategy on past data")
    bt.add_argument("--start", required=True, help="YYYY-MM-DD")
    bt.add_argument("--end", required=True, help="YYYY-MM-DD")
    cmp = sub.add_parser("compare", help="backtest 1/5/15-min candles x several targets, long and short")
    cmp.add_argument("--start", required=True, help="YYYY-MM-DD")
    cmp.add_argument("--end", required=True, help="YYYY-MM-DD")
    sub.add_parser("live", help="paper trade in real time")
    args = parser.parse_args()

    load_dotenv()
    cfg = load_config(args.config)
    if args.command == "check":
        cmd_check(cfg)
    elif args.command == "backtest":
        cmd_backtest(cfg, args.start, args.end)
    elif args.command == "compare":
        cmd_compare(cfg, args.start, args.end)
    else:
        cmd_live(cfg)


if __name__ == "__main__":
    main()
