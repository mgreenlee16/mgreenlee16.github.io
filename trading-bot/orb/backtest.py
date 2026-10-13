"""Replays the ORB rules over historical 1-minute bars.

Assumptions (kept deliberately conservative):
- You get filled at the OPEN of the first 1-minute bar after the breakout
  candle closes, plus slippage.
- If a single 1-minute bar touches both the stop and the target, the stop
  is assumed to have hit first.
- Anything still open at flatten_time is closed at that bar's open.
"""
from dataclasses import asdict, dataclass, replace

import numpy as np
import pandas as pd

from .config import Config
from .strategy import Signal, at_time, find_signal, position_size, trend_bias


@dataclass
class Trade:
    date: object
    symbol: str
    side: str
    entry_time: pd.Timestamp
    entry: float
    stop: float
    target: float
    qty: int
    exit_time: pd.Timestamp
    exit: float
    exit_reason: str
    pnl: float
    r_multiple: float


def split_by_day(bars_by_symbol: dict) -> dict:
    """{symbol: DataFrame} -> {symbol: {date: that day's bars}}"""
    return {sym: {d: g for d, g in df.groupby(df.index.date)} for sym, df in bars_by_symbol.items()}


def simulate_fill_and_exit(sig: Signal, day_bars: pd.DataFrame, cfg: Config):
    """Returns (entry_time, entry_price, exit_time, exit_price, reason) or None."""
    after = day_bars[day_bars.index >= sig.candle_close]
    flatten_at = at_time(day_bars, cfg.flatten_time)
    live = after[after.index < flatten_at]
    if live.empty:
        return None

    slip = cfg.slippage_pct / 100
    is_long = sig.side == "long"
    entry_time = live.index[0]
    entry = live["open"].iloc[0] * (1 + slip if is_long else 1 - slip)

    # A bracket order can't be placed if price already ran past the stop or target.
    if is_long and not (sig.stop < entry < sig.target):
        return None
    if not is_long and not (sig.target < entry < sig.stop):
        return None

    def worse(price):  # slippage on market-style exits
        return price * (1 - slip if is_long else 1 + slip)

    opens, highs, lows = live["open"].to_numpy(), live["high"].to_numpy(), live["low"].to_numpy()
    if is_long:
        stop_hits = np.flatnonzero(lows <= sig.stop)
        target_hits = np.flatnonzero(highs >= sig.target)
    else:
        stop_hits = np.flatnonzero(highs >= sig.stop)
        target_hits = np.flatnonzero(lows <= sig.target)
    first_stop = stop_hits[0] if len(stop_hits) else None
    first_target = target_hits[0] if len(target_hits) else None

    if first_stop is not None and (first_target is None or first_stop <= first_target):
        i = first_stop
        price = min(opens[i], sig.stop) if is_long else max(opens[i], sig.stop)
        return entry_time, entry, live.index[i], worse(price), "stop"
    if first_target is not None:
        i = first_target
        price = max(opens[i], sig.target) if is_long else min(opens[i], sig.target)
        return entry_time, entry, live.index[i], price, "target"
    if len(after) > len(live):
        return entry_time, entry, after.index[len(live)], worse(after["open"].iloc[len(live)]), "flatten"
    return entry_time, entry, live.index[-1], worse(live["close"].iloc[-1]), "close"


def run_backtest(cfg: Config, days_by_symbol: dict, daily_closes: dict | None = None):
    """Returns (trades DataFrame, daily equity Series).

    days_by_symbol comes from split_by_day(). daily_closes ({symbol: Series of
    daily closes indexed by date}) is only needed when trend_filter_days > 0.
    """
    all_days = sorted({d for days in days_by_symbol.values() for d in days})
    equity = cfg.starting_equity
    trades, equity_curve = [], {}

    for day in all_days:
        candidates = []
        for sym, days in days_by_symbol.items():
            day_bars = days.get(day)
            if day_bars is None or day_bars.empty:
                continue
            bias = None
            if cfg.trend_filter_days > 0 and daily_closes and sym in daily_closes:
                closes = daily_closes[sym]
                bias = trend_bias(closes[closes.index < day], cfg.trend_filter_days)
            sig = find_signal(sym, day_bars, cfg, bias=bias)
            if sig is None:
                continue
            sim = simulate_fill_and_exit(sig, day_bars, cfg)
            if sim is not None:
                candidates.append((sig, sim))
        candidates.sort(key=lambda c: c[1][0])  # by entry time

        todays = []
        for sig, (entry_time, entry, exit_time, exit_price, reason) in candidates:
            if len(todays) >= cfg.max_trades_per_day:
                break
            realized = sum(t.pnl for t in todays if t.exit_time <= entry_time)
            if realized <= -equity * cfg.daily_loss_limit_pct / 100:
                break
            qty = position_size(equity, entry, sig.stop, cfg)
            if qty == 0:
                continue
            direction = 1 if sig.side == "long" else -1
            pnl = (exit_price - entry) * qty * direction
            r = pnl / (qty * abs(entry - sig.stop))
            todays.append(Trade(day, sig.symbol, sig.side, entry_time, entry, sig.stop,
                                sig.target, qty, exit_time, exit_price, reason, pnl, r))

        equity += sum(t.pnl for t in todays)
        trades.extend(todays)
        equity_curve[day] = equity

    trades_df = pd.DataFrame([asdict(t) for t in trades])
    return trades_df, pd.Series(equity_curve, name="equity")


def stats(trades: pd.DataFrame, equity: pd.Series, cfg: Config) -> dict:
    if trades.empty:
        return {"trades": 0}
    wins, losses = trades[trades.pnl > 0], trades[trades.pnl <= 0]
    gross_loss = -losses.pnl.sum()
    years = max(len(equity) / 252, 1 / 252)
    final = equity.iloc[-1] / cfg.starting_equity
    return {
        "trades": len(trades),
        "win_rate": len(wins) / len(trades) * 100,
        "total_return": (final - 1) * 100,
        "annual_return": (final ** (1 / years) - 1) * 100 if final > 0 else -100.0,
        "max_drawdown": ((equity - equity.cummax()) / equity.cummax()).min() * 100,
        "profit_factor": wins.pnl.sum() / gross_loss if gross_loss > 0 else float("inf"),
        "avg_r": trades.r_multiple.mean(),
        "avg_win": wins.pnl.mean() if len(wins) else 0.0,
        "avg_loss": losses.pnl.mean() if len(losses) else 0.0,
    }


def summarize(trades: pd.DataFrame, equity: pd.Series, cfg: Config) -> str:
    if trades.empty:
        return "No trades were taken. Try a longer date range or looser settings."
    s = stats(trades, equity, cfg)
    by_year = trades.groupby(pd.to_datetime(trades.date).dt.year).agg(
        trades=("pnl", "size"), win_rate=("pnl", lambda p: (p > 0).mean() * 100),
        pnl=("pnl", "sum"), avg_r=("r_multiple", "mean"))

    lines = [
        "=" * 56,
        f"ORB backtest  {equity.index[0]} -> {equity.index[-1]}  ({len(equity)} trading days)",
        f"{cfg.signal_timeframe_minutes}-min candles | {cfg.direction} | target {cfg.reward_risk}R"
        f" | stop {cfg.stop_mode}"
        + (f" | trend filter {cfg.trend_filter_days}d" if cfg.trend_filter_days else ""),
        "=" * 56,
        f"Starting equity     ${cfg.starting_equity:,.0f}",
        f"Ending equity       ${equity.iloc[-1]:,.0f}",
        f"Total return        {s['total_return']:+.2f}%",
        f"Annual return       {s['annual_return']:+.2f}%",
        f"Max drawdown        {s['max_drawdown']:.2f}%",
        f"Trades              {s['trades']}",
        f"Win rate            {s['win_rate']:.1f}%",
        f"Average win         ${s['avg_win']:,.2f}",
        f"Average loss        ${s['avg_loss']:,.2f}",
        f"Profit factor       {s['profit_factor']:.2f}   (above 1.0 = made money)",
        f"Average R / trade   {s['avg_r']:+.3f}R",
        "",
        "How trades ended:",
        trades.exit_reason.value_counts().to_string(),
        "",
        "By year (does it work every year, or just one lucky one?):",
        by_year.round(2).to_string(),
        "",
        "By side:",
        trades.groupby("side").agg(trades=("pnl", "size"), pnl=("pnl", "sum"),
                                   avg_r=("r_multiple", "mean")).round(2).to_string(),
        "",
        "By symbol:",
        trades.groupby("symbol").agg(trades=("pnl", "size"), pnl=("pnl", "sum"),
                                     avg_r=("r_multiple", "mean")).round(2).to_string(),
    ]
    return "\n".join(lines)


def compare(cfg: Config, days_by_symbol: dict, daily_closes: dict | None = None,
            timeframes=(1, 5, 15), targets=(1.0, 1.5, 2.0, 2.5, 3.0),
            directions=("long", "short")) -> pd.DataFrame:
    """Re-runs the backtest for every combination of candle size, profit
    target and direction (the experiment from the ORB timeframe video)."""
    rows = []
    for direction in directions:
        for tf in timeframes:
            for rr in targets:
                c = replace(cfg, signal_timeframe_minutes=tf, reward_risk=rr, direction=direction)
                trades, equity = run_backtest(c, days_by_symbol, daily_closes)
                rows.append({"direction": direction, "candle_min": tf, "target_R": rr,
                             **stats(trades, equity, c)})
                print(f"  done: {direction:5s} {tf:2d}-min {rr}R", flush=True)
    cols = ["direction", "candle_min", "target_R", "trades", "win_rate", "annual_return",
            "max_drawdown", "profit_factor", "avg_r"]
    df = pd.DataFrame(rows)
    return df[[c for c in cols if c in df.columns]]
