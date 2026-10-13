"""Runs the ORB strategy against an Alpaca PAPER account in real time.

Each minute after the opening range is set, the bot downloads today's
1-minute bars, checks every symbol for a breakout, and sends a bracket
order (entry + stop loss + profit target together) when it finds one.
At flatten_time it closes everything.
"""
import logging
import time as systime
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import (GetOrdersRequest, MarketOrderRequest, StopLossRequest,
                                     TakeProfitRequest)

from .config import Config
from .data import api_keys, fetch_daily_closes, fetch_minute_bars, make_data_client
from .strategy import MARKET_OPEN, find_signal, position_size, trend_bias

NY = ZoneInfo("America/New_York")
# Ignore a breakout if the bot only notices it this long after the candle closed
# (e.g. it was started late). Chasing old breakouts isn't the strategy.
MAX_SIGNAL_AGE = timedelta(minutes=2)

log = logging.getLogger("orb")


def setup_logging():
    Path("logs").mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    file_handler = logging.FileHandler(f"logs/live_{datetime.now(NY):%Y-%m-%d}.log")
    file_handler.setFormatter(fmt)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    log.setLevel(logging.INFO)
    log.handlers = [file_handler, console]


class LiveTrader:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        # paper=True is hard-coded on purpose: this bot never touches real money.
        self.trading = TradingClient(*api_keys(), paper=True)
        self.data = make_data_client()
        self.day = None
        self.done_symbols: set[str] = set()   # traded or skipped for the day
        self.trades_today = 0
        self.flattened = False
        self.bias: dict[str, str | None] = {}

    # ---------- daily state ----------
    def _new_day(self, today):
        self.day = today
        self.done_symbols = set()
        self.trades_today = 0
        self.flattened = False
        self.bias = {}
        # If the bot was restarted mid-day, don't re-trade symbols it already traded.
        session_start = datetime.combine(today, MARKET_OPEN, NY)
        orders = self.trading.get_orders(GetOrdersRequest(
            status=QueryOrderStatus.ALL, after=session_start, limit=500))
        traded = {o.symbol for o in orders if o.symbol in self.cfg.symbols}
        self.done_symbols |= traded
        self.trades_today = len(traded)
        log.info("New trading day %s. Watching %s. Already traded: %s",
                 today, ", ".join(self.cfg.symbols), ", ".join(sorted(traded)) or "none")
        if self.cfg.trend_filter_days > 0:
            n = self.cfg.trend_filter_days
            closes = fetch_daily_closes(self.data, self.cfg.symbols,
                                        session_start - timedelta(days=n * 2 + 10),
                                        session_start - timedelta(hours=9), self.cfg.live_data_feed)
            for sym in self.cfg.symbols:
                series = closes.get(sym)
                if series is not None:
                    series = series[series.index < today]
                self.bias[sym] = trend_bias(series, n)
            log.info("Trend (%d-day average): %s", n,
                     ", ".join(f"{s} {b or 'unknown'}" for s, b in self.bias.items()))

    def _daily_loss_hit(self) -> bool:
        acct = self.trading.get_account()
        equity, last = float(acct.equity), float(acct.last_equity)
        change_pct = (equity - last) / last * 100 if last else 0.0
        if change_pct <= -self.cfg.daily_loss_limit_pct:
            log.warning("Daily loss limit hit (%.2f%%). No new trades today.", change_pct)
            return True
        return False

    # ---------- main loop ----------
    def run(self):
        acct = self.trading.get_account()
        log.info("Connected to Alpaca PAPER account. Equity $%s, buying power $%s",
                 acct.equity, acct.buying_power)
        while True:
            try:
                wait = self._tick()
            except KeyboardInterrupt:
                raise
            except Exception:
                log.exception("Error in main loop; retrying in 30s")
                wait = 30
            systime.sleep(max(1, wait))

    def _tick(self) -> float:
        """Does one round of work and returns how many seconds to sleep."""
        clock = self.trading.get_clock()
        now = clock.timestamp.astimezone(NY)

        if not clock.is_open:
            until_open = (clock.next_open.astimezone(NY) - now).total_seconds()
            log.info("Market closed. Next open %s.", clock.next_open.astimezone(NY))
            return min(until_open + 5, 30 * 60)

        if self.day != now.date():
            self._new_day(now.date())

        # Close everything a few minutes before the close (handles half days too).
        flatten_at = min(datetime.combine(now.date(), self.cfg.flatten_time, NY),
                         clock.next_close.astimezone(NY) - timedelta(minutes=5))
        if now >= flatten_at:
            if not self.flattened:
                log.info("Flatten time: closing all positions and cancelling orders.")
                self.trading.close_all_positions(cancel_orders=True)
                self.flattened = True
            return 60

        session_open = datetime.combine(now.date(), MARKET_OPEN, NY)
        or_end = session_open + timedelta(minutes=self.cfg.opening_range_minutes)
        if now < or_end:
            log.info("Building the opening range until %s.", or_end.strftime("%H:%M"))
            return (or_end - now).total_seconds() + 5

        last_entry = datetime.combine(now.date(), self.cfg.last_entry_time, NY)
        if now > last_entry + timedelta(minutes=1):
            return 60
        if self.trades_today >= self.cfg.max_trades_per_day:
            return 60
        if self._daily_loss_hit():
            self.trades_today = self.cfg.max_trades_per_day
            return 60

        self._scan(now, session_open)
        # Wake up 5 seconds after the next minute so that minute's bar is published.
        next_minute = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        return (next_minute - now).total_seconds() + 5

    def _scan(self, now, session_open):
        symbols = [s for s in self.cfg.symbols if s not in self.done_symbols]
        if not symbols:
            return
        bars = fetch_minute_bars(self.data, symbols, session_open, now, self.cfg.live_data_feed)
        for symbol in symbols:
            day_bars = bars.get(symbol)
            if day_bars is None or day_bars.empty:
                continue
            # Only use fully finished 1-minute bars.
            day_bars = day_bars[day_bars.index + timedelta(minutes=1) <= now]
            sig = find_signal(symbol, day_bars, self.cfg, now=now, bias=self.bias.get(symbol))
            if sig is None:
                continue
            self.done_symbols.add(symbol)
            if now - sig.candle_close > MAX_SIGNAL_AGE:
                log.info("%s broke out at %s but that's too old to chase; skipping today.",
                         symbol, sig.candle_close.strftime("%H:%M"))
                continue
            if self.trades_today >= self.cfg.max_trades_per_day:
                log.info("%s signal ignored: max trades for the day reached.", symbol)
                continue
            self._enter(sig)

    def _enter(self, sig):
        log.info("SIGNAL %s %s: close %.2f outside range %.2f-%.2f | stop %.2f target %.2f",
                 sig.side.upper(), sig.symbol, sig.entry, sig.range_low, sig.range_high,
                 sig.stop, sig.target)
        if sig.side == "short":
            asset = self.trading.get_asset(sig.symbol)
            if not (asset.shortable and asset.easy_to_borrow):
                log.info("%s is not shortable right now; skipping.", sig.symbol)
                return

        equity = float(self.trading.get_account().equity)
        qty = position_size(equity, sig.entry, sig.stop, self.cfg)
        if qty < 1:
            log.info("%s position size rounds to 0 shares; skipping.", sig.symbol)
            return

        order = MarketOrderRequest(
            symbol=sig.symbol,
            qty=qty,
            side=OrderSide.BUY if sig.side == "long" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=round(sig.target, 2)),
            stop_loss=StopLossRequest(stop_price=round(sig.stop, 2)),
        )
        try:
            placed = self.trading.submit_order(order)
        except Exception as e:
            log.error("Order for %s rejected: %s", sig.symbol, e)
            return
        self.trades_today += 1
        risk = qty * sig.risk_per_share
        log.info("ORDER %s %d %s (risking ~$%.0f). Order id %s",
                 "BUY" if sig.side == "long" else "SELL SHORT", qty, sig.symbol, risk, placed.id)
