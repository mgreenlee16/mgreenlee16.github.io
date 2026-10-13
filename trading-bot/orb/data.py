"""Downloads 1-minute bars from Alpaca and caches them to disk."""
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

NY = "America/New_York"
COLUMNS = ["open", "high", "low", "close", "volume"]
CACHE_DIR = Path("data")


def api_keys():
    key = os.getenv("ALPACA_API_KEY")
    secret = os.getenv("ALPACA_SECRET_KEY")
    if not key or not secret or "your_paper" in key:
        raise SystemExit(
            "Missing Alpaca keys. Copy .env.example to .env and paste in your paper trading keys."
        )
    return key, secret


def make_data_client() -> StockHistoricalDataClient:
    return StockHistoricalDataClient(*api_keys())


def fetch_minute_bars(client, symbols, start: datetime, end: datetime, feed: str) -> dict:
    """Regular-session (9:30-16:00 ET) 1-minute bars, one DataFrame per symbol."""
    req = StockBarsRequest(
        symbol_or_symbols=list(symbols),
        timeframe=TimeFrame.Minute,
        start=start,
        end=end,
        feed=DataFeed(feed),
        adjustment=Adjustment.SPLIT,
    )
    df = client.get_stock_bars(req).df
    if df.empty:
        return {}
    df = df.reset_index()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(NY)
    out = {}
    for symbol, g in df.groupby("symbol"):
        g = g.set_index("timestamp")[COLUMNS].sort_index()
        out[symbol] = g.between_time("09:30", "15:59")
    return out


def load_backtest_bars(client, symbols, start: str, end: str, feed: str) -> dict:
    """Same as fetch_minute_bars but saves to data/ so re-runs are instant."""
    CACHE_DIR.mkdir(exist_ok=True)
    bars, missing = {}, []
    for symbol in symbols:
        path = CACHE_DIR / f"{symbol}_{start}_{end}_{feed}.csv"
        if path.exists():
            df = pd.read_csv(path, index_col=0)
            df.index = pd.to_datetime(df.index, utc=True).tz_convert(NY)
            bars[symbol] = df
        else:
            missing.append(symbol)

    if missing:
        print(f"Downloading 1-minute bars for {', '.join(missing)} ({start} to {end})...")
        start_dt = pd.Timestamp(start, tz=NY).to_pydatetime()
        end_dt = (pd.Timestamp(end, tz=NY) + pd.Timedelta(days=1)).to_pydatetime()
        fetched = fetch_minute_bars(client, missing, start_dt, end_dt, feed)
        for symbol, df in fetched.items():
            df.to_csv(CACHE_DIR / f"{symbol}_{start}_{end}_{feed}.csv")
            bars[symbol] = df
        for symbol in set(missing) - set(fetched):
            print(f"  warning: no data returned for {symbol}")
    return bars
