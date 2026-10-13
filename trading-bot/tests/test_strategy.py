"""Checks the ORB rules on made-up price data. Run with:  python -m pytest"""
from datetime import time

import pandas as pd

from orb.backtest import compare, run_backtest, simulate_fill_and_exit, split_by_day
from orb.config import Config
from orb.strategy import find_signal, opening_range, position_size, trend_bias


def make_day(path, date="2025-03-04"):
    """Build 1-minute bars from 9:30 where each bar opens at the previous close
    and closes at the next price in `path`; the rest of the day stays flat."""
    idx = pd.date_range(f"{date} 09:30", f"{date} 15:59", freq="1min", tz="America/New_York")
    closes = list(path) + [path[-1]] * (len(idx) - len(path))
    opens = [closes[0]] + closes[:-1]
    df = pd.DataFrame({"open": opens, "close": closes}, index=idx)
    df["high"] = df[["open", "close"]].max(axis=1) + 0.05
    df["low"] = df[["open", "close"]].min(axis=1) - 0.05
    df["volume"] = 1000
    return df


def cfg(**overrides):
    """5-minute candles, both directions, 2R: makes the made-up days below short."""
    settings = dict(signal_timeframe_minutes=5, direction="both", reward_risk=2.0,
                    max_position_pct=25.0)
    settings.update(overrides)
    return Config(symbols=["TEST"], **settings)


def backtest(c, day, daily_closes=None):
    return run_backtest(c, split_by_day({"TEST": day}), daily_closes)


# 15 quiet minutes between ~100 and ~101, then a push above the range.
RANGE = [100.5, 100.0, 101.0, 100.5] * 3 + [100.4, 100.6, 100.5]
BREAKOUT_UP = RANGE + [100.8, 101.2, 101.4, 101.5, 101.6]


def test_opening_range_uses_first_15_minutes():
    day = make_day(BREAKOUT_UP)
    high, low = opening_range(day, cfg())
    assert high == 101.05 and low == 99.95


def test_long_signal_on_5min_close_above_range():
    sig = find_signal("TEST", make_day(BREAKOUT_UP), cfg())
    assert sig.side == "long"
    assert sig.candle_close == pd.Timestamp("2025-03-04 09:50", tz="America/New_York")
    assert sig.entry == 101.6
    assert sig.stop == 99.95                       # opposite side of the range
    assert round(sig.target, 2) == round(101.6 + 2 * (101.6 - 99.95), 2)


def test_short_signal_and_direction_filter():
    down = RANGE + [100.0, 99.7, 99.5, 99.4, 99.3]
    sig = find_signal("TEST", make_day(down), cfg())
    assert sig.side == "short" and sig.stop == 101.05
    assert find_signal("TEST", make_day(down), cfg(direction="long")) is None


def test_stop_modes():
    day = make_day(BREAKOUT_UP)
    assert find_signal("TEST", day, cfg(stop_mode="midpoint")).stop == (101.05 + 99.95) / 2
    assert find_signal("TEST", day, cfg(stop_mode="candle")).stop == 100.45  # breakout candle low


def test_live_mode_ignores_unfinished_candle():
    day = make_day(BREAKOUT_UP)
    early = pd.Timestamp("2025-03-04 09:49", tz="America/New_York")
    assert find_signal("TEST", day, cfg(), now=early) is None
    assert find_signal("TEST", day, cfg(), now=early + pd.Timedelta(minutes=1)) is not None


def test_no_signal_after_last_entry_time():
    late = RANGE + [100.5] * 200 + [102.0] * 10   # breaks out around 13:05
    assert find_signal("TEST", make_day(late), cfg(last_entry_time=time(11, 30))) is None


def test_range_filter():
    assert find_signal("TEST", make_day(BREAKOUT_UP), cfg(max_range_pct=0.5)) is None


def test_position_size_by_risk_and_cap():
    c = cfg()
    assert position_size(100_000, 100.0, 99.0, c) == 250    # capped by 25% of account
    assert position_size(100_000, 100.0, 95.0, c) == 200    # $1,000 risk / $5 per share


def test_backtest_hits_target():
    up = BREAKOUT_UP + [102, 103, 104, 105, 106]
    day = make_day(up)
    c = cfg(slippage_pct=0)
    sig = find_signal("TEST", day, c)
    entry_time, entry, _, exit_price, reason = simulate_fill_and_exit(sig, day, c)
    assert reason == "target" and exit_price == sig.target and entry == 101.6

    trades, equity = backtest(c, day)
    assert len(trades) == 1 and trades.pnl.iloc[0] > 0
    assert equity.iloc[-1] > c.starting_equity


def test_backtest_hits_stop():
    day = make_day(BREAKOUT_UP + [101.0, 100.0, 99.0])
    trades, _ = backtest(cfg(slippage_pct=0), day)
    assert trades.exit_reason.iloc[0] == "stop"
    assert round(trades.r_multiple.iloc[0], 2) == -1.0


def test_backtest_flattens_at_end_of_day():
    trades, _ = backtest(cfg(slippage_pct=0), make_day(BREAKOUT_UP))
    assert trades.exit_reason.iloc[0] == "flatten"
    assert trades.exit_time.iloc[0].time() == time(15, 55)


def test_video_defaults_use_15min_candle_and_enter_next_open():
    c = Config(symbols=["TEST"], slippage_pct=0)   # defaults: 15-min, long only, 1.5R
    day = make_day(RANGE + [100.8, 101.2, 101.4, 101.5, 101.6] + [101.7] * 10)
    sig = find_signal("TEST", day, c)
    assert sig.side == "long"
    assert sig.candle_close == pd.Timestamp("2025-03-04 10:00", tz="America/New_York")
    assert round(sig.target - sig.entry, 4) == round(1.5 * (sig.entry - sig.stop), 4)
    entry_time, *_ = simulate_fill_and_exit(sig, day, c)
    assert entry_time == sig.candle_close              # open of the next candle


def test_long_only_waits_past_a_downside_break():
    down_then_up = RANGE + [99.5] * 5 + [100.5] * 5 + [101.5] * 5
    sig = find_signal("TEST", make_day(down_then_up), cfg(direction="long"))
    assert sig.side == "long"


def test_trend_bias():
    closes = pd.Series([10, 11, 12, 13, 14.0])
    assert trend_bias(closes, 3) == "up"
    assert trend_bias(closes[::-1].reset_index(drop=True), 3) == "down"
    assert trend_bias(closes, 10) is None               # not enough history


def test_trend_filter_blocks_trades_against_trend():
    day = make_day(BREAKOUT_UP)
    on = cfg(trend_filter_days=3)
    assert find_signal("TEST", day, on, bias="up").side == "long"
    assert find_signal("TEST", day, on, bias="down") is None
    assert find_signal("TEST", day, on, bias=None) is None

    d = day.index[0].date()
    prior = pd.date_range(end=pd.Timestamp(d) - pd.Timedelta(days=1), periods=5, freq="B").date
    rising = {"TEST": pd.Series([90, 92, 94, 96, 98.0], index=prior)}
    falling = {"TEST": pd.Series([98, 96, 94, 92, 90.0], index=prior)}
    assert len(backtest(on, day, rising)[0]) == 1
    assert len(backtest(on, day, falling)[0]) == 0


def test_compare_runs_every_combination():
    days = split_by_day({"TEST": make_day(BREAKOUT_UP)})
    table = compare(cfg(), days, timeframes=(1, 5), targets=(1.5, 2.0), directions=("long",))
    assert len(table) == 4 and set(table.candle_min) == {1, 5}
