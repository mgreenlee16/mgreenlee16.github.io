"""Command-line entry point.

    python run.py check                                   # test your API keys
    python run.py backtest --start 2025-01-01 --end 2025-12-31
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


def cmd_backtest(cfg, start, end):
    from orb.backtest import run_backtest, summarize
    from orb.data import load_backtest_bars, make_data_client

    bars = load_backtest_bars(make_data_client(), cfg.symbols, start, end, cfg.backtest_data_feed)
    trades, equity = run_backtest(cfg, bars)
    print(summarize(trades, equity, cfg))
    if not trades.empty:
        Path("results").mkdir(exist_ok=True)
        trades.to_csv("results/trades.csv", index=False)
        equity.to_csv("results/equity.csv", index_label="date")
        print("\nEvery trade saved to results/trades.csv, daily equity to results/equity.csv")


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
    sub.add_parser("live", help="paper trade in real time")
    args = parser.parse_args()

    load_dotenv()
    cfg = load_config(args.config)
    if args.command == "check":
        cmd_check(cfg)
    elif args.command == "backtest":
        cmd_backtest(cfg, args.start, args.end)
    else:
        cmd_live(cfg)


if __name__ == "__main__":
    main()
