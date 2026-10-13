"""The ORB rules themselves. Used by both the backtester and the live bot,
so what you backtest is exactly what trades.

Input everywhere is a DataFrame of 1-minute bars for ONE symbol and ONE day,
indexed by US/Eastern timestamps (bar start time), with columns
open/high/low/close/volume.
"""
import math
from dataclasses import dataclass
from datetime import datetime, time, timedelta

import pandas as pd

from .config import Config

MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)


@dataclass
class Signal:
    symbol: str
    side: str                  # "long" or "short"
    candle_close: pd.Timestamp  # when the breakout candle closed (earliest possible entry)
    entry: float               # close of the breakout candle
    stop: float
    target: float
    range_high: float
    range_low: float

    @property
    def risk_per_share(self) -> float:
        return abs(self.entry - self.stop)


def at_time(day_bars: pd.DataFrame, t: time) -> pd.Timestamp:
    """Timestamp for clock time `t` on the same day as `day_bars`."""
    return day_bars.index[0].replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)


def session_open(day_bars: pd.DataFrame) -> pd.Timestamp:
    return at_time(day_bars, MARKET_OPEN)


def opening_range(day_bars: pd.DataFrame, cfg: Config):
    """High and low of the first `opening_range_minutes` of the session, or None."""
    start = session_open(day_bars)
    end = start + timedelta(minutes=cfg.opening_range_minutes)
    or_bars = day_bars[(day_bars.index >= start) & (day_bars.index < end)]
    if or_bars.empty:
        return None
    return float(or_bars["high"].max()), float(or_bars["low"].min())


def signal_candles(day_bars: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """1-minute bars after the opening range, rolled up into signal-timeframe candles."""
    or_end = session_open(day_bars) + timedelta(minutes=cfg.opening_range_minutes)
    after = day_bars[day_bars.index >= or_end]
    if after.empty:
        return after
    tf = f"{cfg.signal_timeframe_minutes}min"
    candles = after.resample(tf, origin=or_end, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    return candles.dropna(subset=["close"])


def find_signal(symbol: str, day_bars: pd.DataFrame, cfg: Config, now: datetime | None = None):
    """Return the first breakout Signal of the day, or None.

    `now` is the current time in live trading; only candles that have fully
    closed by `now` are looked at. In a backtest leave it as None.
    """
    if day_bars.empty:
        return None
    or_end = session_open(day_bars) + timedelta(minutes=cfg.opening_range_minutes)
    if now is not None and now < or_end:
        return None

    rng = opening_range(day_bars, cfg)
    if rng is None:
        return None
    high, low = rng
    range_pct = (high - low) / ((high + low) / 2) * 100
    if not (cfg.min_range_pct <= range_pct <= cfg.max_range_pct):
        return None

    tf = timedelta(minutes=cfg.signal_timeframe_minutes)
    cutoff = at_time(day_bars, cfg.last_entry_time)

    for start, c in signal_candles(day_bars, cfg).iterrows():
        closed_at = start + tf
        if closed_at > cutoff:
            break
        if now is not None and closed_at > now:
            break

        side = None
        if c["close"] > high and cfg.direction in ("both", "long"):
            side = "long"
        elif c["close"] < low and cfg.direction in ("both", "short"):
            side = "short"
        if side is None:
            continue

        entry = float(c["close"])
        if cfg.stop_mode == "opposite":
            stop = low if side == "long" else high
        elif cfg.stop_mode == "midpoint":
            stop = (high + low) / 2
        else:  # candle
            stop = float(c["low"]) if side == "long" else float(c["high"])

        risk = entry - stop if side == "long" else stop - entry
        if risk <= 0:
            # Can happen with stop_mode=candle on an odd candle; skip it.
            continue
        target = entry + cfg.reward_risk * risk if side == "long" else entry - cfg.reward_risk * risk
        return Signal(symbol, side, closed_at, entry, stop, target, high, low)

    return None


def position_size(equity: float, entry: float, stop: float, cfg: Config) -> int:
    """Shares to buy so a stop-out loses about risk_per_trade_pct of the account,
    capped so the position is never bigger than max_position_pct of the account."""
    risk_per_share = abs(entry - stop)
    if risk_per_share <= 0 or entry <= 0:
        return 0
    by_risk = (equity * cfg.risk_per_trade_pct / 100) / risk_per_share
    by_size = (equity * cfg.max_position_pct / 100) / entry
    return max(0, math.floor(min(by_risk, by_size)))
