"""Replays the ORB rules over historical 1-minute bars.

Assumptions (kept deliberately conservative):
- You get filled at the OPEN of the first 1-minute bar after the breakout
  candle closes, plus slippage.
- If a single 1-minute bar touches both the stop and the target, the stop
  is assumed to have hit first.
- Anything still open at flatten_time is closed at that bar's open.
"""
from dataclasses import asdict, dataclass

import pandas as pd

from .config import Config
from .strategy import Signal, at_time, find_signal, position_size


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


def simulate_fill_and_exit(sig: Signal, day_bars: pd.DataFrame, cfg: Config):
    """Returns (entry_time, entry_price, exit_time, exit_price, reason) or None."""
    after = day_bars[day_bars.index >= sig.candle_close]
    flatten_at = at_time(day_bars, cfg.flatten_time)
    if after.empty or after.index[0] >= flatten_at:
        return None

    slip = cfg.slippage_pct / 100
    is_long = sig.side == "long"
    entry_time = after.index[0]
    entry = after.iloc[0]["open"] * (1 + slip if is_long else 1 - slip)

    # A bracket order can't be placed if price already ran past the stop or target.
    if is_long and not (sig.stop < entry < sig.target):
        return None
    if not is_long and not (sig.target < entry < sig.stop):
        return None

    def worse(price):  # slippage on market-style exits
        return price * (1 - slip if is_long else 1 + slip)

    for ts, bar in after.iterrows():
        if ts >= flatten_at:
            return entry_time, entry, ts, worse(bar["open"]), "flatten"
        if is_long:
            if bar["low"] <= sig.stop:
                return entry_time, entry, ts, worse(min(bar["open"], sig.stop)), "stop"
            if bar["high"] >= sig.target:
                return entry_time, entry, ts, max(bar["open"], sig.target), "target"
        else:
            if bar["high"] >= sig.stop:
                return entry_time, entry, ts, worse(max(bar["open"], sig.stop)), "stop"
            if bar["low"] <= sig.target:
                return entry_time, entry, ts, min(bar["open"], sig.target), "target"

    last_ts = after.index[-1]
    return entry_time, entry, last_ts, worse(after.iloc[-1]["close"]), "close"


def run_backtest(cfg: Config, bars_by_symbol: dict):
    """Returns (trades DataFrame, daily equity Series)."""
    days_by_symbol = {
        sym: {d: g for d, g in df.groupby(df.index.date)} for sym, df in bars_by_symbol.items()
    }
    all_days = sorted({d for days in days_by_symbol.values() for d in days})

    equity = cfg.starting_equity
    trades, equity_curve = [], {}

    for day in all_days:
        candidates = []
        for sym, days in days_by_symbol.items():
            day_bars = days.get(day)
            if day_bars is None or day_bars.empty:
                continue
            sig = find_signal(sym, day_bars, cfg)
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


def summarize(trades: pd.DataFrame, equity: pd.Series, cfg: Config) -> str:
    if trades.empty:
        return "No trades were taken. Try a longer date range or looser settings."

    wins = trades[trades.pnl > 0]
    losses = trades[trades.pnl <= 0]
    gross_win, gross_loss = wins.pnl.sum(), -losses.pnl.sum()
    profit_factor = gross_win / gross_loss if gross_loss > 0 else float("inf")
    peak = equity.cummax()
    max_dd = ((equity - peak) / peak).min() * 100
    total_return = (equity.iloc[-1] / cfg.starting_equity - 1) * 100

    lines = [
        "=" * 52,
        f"ORB backtest  {equity.index[0]} -> {equity.index[-1]}  ({len(equity)} trading days)",
        "=" * 52,
        f"Starting equity     ${cfg.starting_equity:,.0f}",
        f"Ending equity       ${equity.iloc[-1]:,.0f}",
        f"Total return        {total_return:+.2f}%",
        f"Max drawdown        {max_dd:.2f}%",
        f"Trades              {len(trades)}",
        f"Win rate            {len(wins) / len(trades) * 100:.1f}%",
        f"Average win         ${wins.pnl.mean() if len(wins) else 0:,.2f}",
        f"Average loss        ${losses.pnl.mean() if len(losses) else 0:,.2f}",
        f"Profit factor       {profit_factor:.2f}   (above 1.0 = made money)",
        f"Average R / trade   {trades.r_multiple.mean():+.3f}R",
        "",
        "How trades ended:",
        trades.exit_reason.value_counts().to_string(),
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
