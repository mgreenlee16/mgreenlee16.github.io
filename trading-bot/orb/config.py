"""Loads config.yaml into a typed Config object."""
from dataclasses import dataclass, fields
from datetime import time

import yaml

STOP_MODES = ("opposite", "midpoint", "candle")
DIRECTIONS = ("both", "long", "short")


def _parse_time(value) -> time:
    if isinstance(value, time):
        return value
    hour, minute = str(value).split(":")
    return time(int(hour), int(minute))


@dataclass
class Config:
    symbols: list
    opening_range_minutes: int = 15
    signal_timeframe_minutes: int = 15
    direction: str = "long"
    last_entry_time: time = time(11, 30)
    min_range_pct: float = 0.0
    max_range_pct: float = 100.0
    trend_filter_days: int = 0
    stop_mode: str = "opposite"
    reward_risk: float = 1.5
    flatten_time: time = time(15, 55)
    risk_per_trade_pct: float = 1.0
    max_position_pct: float = 100.0
    max_trades_per_day: int = 2
    daily_loss_limit_pct: float = 3.0
    live_data_feed: str = "iex"
    backtest_data_feed: str = "sip"
    starting_equity: float = 100_000
    slippage_pct: float = 0.02

    def __post_init__(self):
        self.symbols = [s.upper() for s in self.symbols]
        self.last_entry_time = _parse_time(self.last_entry_time)
        self.flatten_time = _parse_time(self.flatten_time)
        if self.stop_mode not in STOP_MODES:
            raise ValueError(f"stop_mode must be one of {STOP_MODES}")
        if self.direction not in DIRECTIONS:
            raise ValueError(f"direction must be one of {DIRECTIONS}")
        if self.reward_risk <= 0:
            raise ValueError("reward_risk must be positive")


def load_config(path: str = "config.yaml") -> Config:
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    known = {f.name for f in fields(Config)}
    unknown = set(raw) - known
    if unknown:
        raise ValueError(f"Unknown setting(s) in {path}: {', '.join(sorted(unknown))}")
    return Config(**raw)
