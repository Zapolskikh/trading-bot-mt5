from dataclasses import dataclass, field
from datetime import datetime, time

import pandas as pd

from trading_bot_mt5.strategies.orb.models import (
    Candle,
    ConfirmationInfo,
    OpeningRange,
    RangePeriod,
    Signal,
    SignalType,
    Timeframe,
    TradingSession,
)
from trading_bot_mt5.strategies.orb.utils import normalize_candle_data


@dataclass(frozen=True, slots=True)
class ConfirmationConfig:
    # Require candle to close outside range (vs just wick)
    require_close: bool = True

    # Number of consecutive closes required outside range
    consecutive_closes: int = 1


@dataclass(slots=True)
class ORBConfig:
    range_timeframe: Timeframe
    range_period: RangePeriod = RangePeriod.MIN_15
    session: TradingSession = field(
        default_factory=lambda: TradingSession(start=time(9, 30), end=time(16, 0), name="Default")
    )
    confirmation: ConfirmationConfig = field(default_factory=ConfirmationConfig)

    # Risk management
    use_range_stop_loss: bool = True  # Use opposite side of range as SL
    stop_loss_buffer_pct: float = 0.1  # Buffer % added to stop loss
    risk_reward_target: float = 2.0  # R:R ratio for take profit

    # Filters
    min_range_size: float | None = None  # Minimum range size in price
    max_range_size: float | None = None  # Maximum range size in price

    # Time filters
    no_trade_after: time = time(11, 00)  # Stop taking new trades after this time


class ORBStrategy:
    """
    Opening Range Breakout Strategy.

    The strategy identifies the high and low of the opening range period,
    then generates signals when price breaks out with confirmation.
    """

    def __init__(self, config: ORBConfig):
        self.config = config
        self._opening_range: OpeningRange | None = None
        self._range_candles: list[Candle] = []
        self._signal_generated: bool = False
        self._current_date: datetime | None = None
        self._consecutive_breakout_closes: int = 0
        self._pending_breakout_direction: SignalType = SignalType.NONE

    def reset(self) -> None:
        """Reset strategy state for a new session."""
        self._opening_range = None
        self._range_candles = []
        self._signal_generated = False
        self._current_date = None
        self._consecutive_breakout_closes = 0
        self._pending_breakout_direction = SignalType.NONE

    @property
    def opening_range(self) -> OpeningRange | None:
        """Get the current opening range."""
        return self._opening_range

    @property
    def is_range_established(self) -> bool:
        """Check if opening range has been established."""
        return self._opening_range is not None

    def _is_new_session(self, candle: Candle) -> bool:
        """Check if this candle starts a new trading session."""
        if self._current_date is None:
            return True
        return candle.timestamp.date() != self._current_date.date()

    def _is_in_opening_range_period(self, candle: Candle) -> bool:
        """Check if candle is within the opening range period."""
        return self.config.session.is_within_opening_range_period(candle.timestamp, self.config.range_period)

    def _is_in_trading_session(self, candle: Candle) -> bool:
        """Check if candle is within the trading session."""
        return self.config.session.is_within_session(candle.timestamp)

    def _can_trade(self, candle: Candle) -> bool:
        """Check if we can take trades at this time."""
        if not self._is_in_trading_session(candle):
            return False

        if self.config.no_trade_after:
            if candle.timestamp.time() > self.config.no_trade_after:
                return False

        return True

    def _build_opening_range(self) -> None:
        """Build the opening range from collected candles."""
        if not self._range_candles:
            return

        high = max(c.high for c in self._range_candles)
        low = min(c.low for c in self._range_candles)
        start_time = self._range_candles[0].timestamp
        end_time = self._range_candles[-1].timestamp

        self._opening_range = OpeningRange(high=high, low=low, start_time=start_time, end_time=end_time)

    def _validate_range(self) -> bool:
        """Validate the opening range against filters."""
        if self._opening_range is None:
            return False

        if self.config.min_range_size and self.config.max_range_size:
            return self._opening_range.allowed_range_size(self.config.min_range_size, self.config.max_range_size)

        return True

    def _check_breakout(self, candle: Candle) -> tuple[SignalType, ConfirmationInfo | None]:
        """
        Check if candle represents a valid breakout with confirmation.
        """
        if self._opening_range is None:
            return SignalType.NONE, None

        orb = self._opening_range
        conf = self.config.confirmation

        # Use confirmation config settings
        require_close = conf.require_close

        signal_type = SignalType.NONE
        breakout_distance = 0.0

        if require_close:
            # Check for close above/below range with buffer
            if candle.close > orb.high:
                signal_type = SignalType.LONG
                breakout_distance = candle.close - orb.high
            elif candle.close < orb.low:
                signal_type = SignalType.SHORT
                breakout_distance = orb.low - candle.close
        else:
            # Check for price breaking range (using high/low)
            if candle.high > orb.high:
                signal_type = SignalType.LONG
                breakout_distance = candle.high - orb.high
            elif candle.low < orb.low:
                signal_type = SignalType.SHORT
                breakout_distance = orb.low - candle.low

        if signal_type == SignalType.NONE:
            # Reset consecutive closes if price comes back inside range
            self._consecutive_breakout_closes = 0
            self._pending_breakout_direction = SignalType.NONE
            return SignalType.NONE, None

        # Handle consecutive closes requirement
        if conf.consecutive_closes > 1:
            if signal_type == self._pending_breakout_direction:
                self._consecutive_breakout_closes += 1
            else:
                self._consecutive_breakout_closes = 1
                self._pending_breakout_direction = signal_type

            if self._consecutive_breakout_closes < conf.consecutive_closes:
                return SignalType.NONE, None

        # Calculate breakout percentage
        breakout_pct = (breakout_distance / orb.range_size * 100) if orb.range_size > 0 else 0

        # Build confirmation info
        confirmation_info = ConfirmationInfo(
            timeframe=self.config.range_timeframe,
            candle=candle,
            breakout_distance=breakout_distance,
            breakout_pct=breakout_pct,
        )

        return signal_type, confirmation_info

    def _calculate_stop_loss(self, signal_type: SignalType) -> float | None:
        """Calculate stop loss level."""
        if not self.config.use_range_stop_loss or self._opening_range is None:
            return None

        orb = self._opening_range
        buffer = orb.range_size * self.config.stop_loss_buffer_pct

        if signal_type == SignalType.LONG:
            return orb.high - buffer
        elif signal_type == SignalType.SHORT:
            return orb.low + buffer

        return None

    def _calculate_take_profit(self, entry_price: float, stop_loss: float, signal_type: SignalType) -> float | None:
        """Calculate take profit level based on R:R ratio."""
        if stop_loss is None:
            return None

        risk = abs(entry_price - stop_loss)
        reward = risk * self.config.risk_reward_target

        if signal_type == SignalType.LONG:
            return entry_price + reward
        elif signal_type == SignalType.SHORT:
            return entry_price - reward

        return None

    def process_candle(self, candle: Candle) -> Signal | None:
        """Process a new candle and potentially generate a signal."""
        # Check for new session
        if self._is_new_session(candle):
            self.reset()
            self._current_date = candle.timestamp

        # Skip if outside trading session
        if not self._is_in_trading_session(candle):
            return None

        # Collect opening range candles
        if self._is_in_opening_range_period(candle):
            self._range_candles.append(candle)
            return None

        # Build opening range when period ends
        if not self.is_range_established and self._range_candles:
            self._build_opening_range()

            # Validate the range
            if not self._validate_range():
                self._opening_range = None
                return None

        # Don't generate signals if range not established
        if not self.is_range_established:
            return None

        # Check if we already generated a signal today
        if self._signal_generated:
            return None

        # Check if we can trade at this time
        if not self._can_trade(candle):
            return None

        # Check for breakout
        signal_type, confirmation_info = self._check_breakout(candle)

        if signal_type == SignalType.NONE:
            return None

        if self._opening_range is None:
            return None

        # Generate signal
        entry_price = (
            (candle.close + self._opening_range.high) / 2
            if signal_type == SignalType.LONG
            else (candle.close + self._opening_range.low) / 2
        )
        stop_loss = self._calculate_stop_loss(signal_type)
        take_profit = None

        if stop_loss is not None:
            take_profit = self._calculate_take_profit(entry_price, stop_loss, signal_type)

        if self._opening_range is None:
            raise ValueError("Opening range should be established at this point")

        signal = Signal(
            signal_type=signal_type,
            timestamp=candle.timestamp,
            entry_price=round(entry_price, 2),
            opening_range=self._opening_range,
            confirmation_candle=candle,
            confirmation_info=confirmation_info,
            stop_loss=round(stop_loss, 2) if stop_loss is not None else None,
            take_profit=round(take_profit, 2) if take_profit is not None else None,
            metadata={
                "range_period": self.config.range_period.value,
                "range_timeframe": self.config.range_timeframe.value,
                "confirmation_timeframe": confirmation_info.timeframe.value if confirmation_info else None,
                "session": self.config.session.name,
                "breakout_distance": confirmation_info.breakout_distance if confirmation_info else None,
                "breakout_pct": confirmation_info.breakout_pct if confirmation_info else None,
            },
        )

        self._signal_generated = True
        return signal

    def process_candles(self, candles: list[Candle] | pd.DataFrame) -> list[Signal]:
        """
        Process multiple candles and return all generated signals.
        """
        if len(candles) == 0:
            return []

        # Normalize input to list of Candles
        candle_list = normalize_candle_data(candles)

        # VWAP
        vwap = self._calculate_vwap(candles)

        signals = []
        for candle in candle_list:
            if self.config.session.is_within_session(candle.timestamp):
                signal = self.process_candle(candle)
                if signal is not None:
                    signal.vwap = vwap
                    signals.append(signal)
        return signals

    def _calculate_vwap(self, candles: list[Candle] | pd.DataFrame) -> float:
        """Calculate VWAP for the given candles."""
        if isinstance(candles, pd.DataFrame):
            df = candles
        else:
            df = pd.DataFrame([c.__dict__ for c in candles])

        if df.empty:
            return 0

        # Filter for regular market hours (>= 09:30 ET)
        market_mask = (df.index.hour > 9) | ((df.index.hour == 9) & (df.index.minute >= 30))
        df = df[market_mask].copy()

        if df.empty:
            return 0

        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        tp_volume = typical_price * df["volume"]

        daily_vol_cum = df["volume"].groupby(pd.Grouper(freq="D")).cumsum()
        df["VWAP"] = tp_volume.groupby(pd.Grouper(freq="D")).cumsum() / daily_vol_cum
        return round(df["VWAP"].iloc[-1], 2)

    def process_dataframe(self, df: pd.DataFrame) -> list[Signal]:
        """
        Process a pandas DataFrame and return all generated signals.

        This is an explicit method for DataFrame input. Equivalent to
        process_candles(df) but makes the intent clearer.
        """
        return self.process_candles(df)

    def process_confirmation_candle(self, candle: Candle, timeframe: Timeframe) -> Signal | None:
        """
        Process a confirmation candle on a different timeframe.

        Use this when you want to:
        1. Build the opening range on one timeframe (e.g., 15m candles)
        2. Confirm breakouts on a different timeframe (e.g., 5m candles)
        """
        # Must have established range first
        if not self.is_range_established:
            return None

        # Check if we already generated a signal today
        if self._signal_generated:
            return None

        # Check if within trading session
        if not self._is_in_trading_session(candle):
            return None

        # Check if we can trade at this time
        if not self._can_trade(candle):
            return None

        # Check for breakout with specified timeframe
        signal_type, confirmation_info = self._check_breakout(candle)

        if signal_type == SignalType.NONE:
            return None

        # Generate signal
        entry_price = candle.close
        stop_loss = self._calculate_stop_loss(signal_type)
        take_profit = None

        if stop_loss is not None:
            take_profit = self._calculate_take_profit(entry_price, stop_loss, signal_type)

        if self._opening_range is None:
            raise ValueError("Opening range should be established at this point")

        signal = Signal(
            signal_type=signal_type,
            timestamp=candle.timestamp,
            entry_price=round(entry_price, 2),
            opening_range=self._opening_range,
            confirmation_candle=candle,
            confirmation_info=confirmation_info,
            stop_loss=round(stop_loss, 2) if stop_loss is not None else None,
            take_profit=round(take_profit, 2) if take_profit is not None else None,
            metadata={
                "range_period": self.config.range_period.value,
                "range_timeframe": self.config.range_timeframe.value,
                "confirmation_timeframe": timeframe.value,
                "session": self.config.session.name,
                "breakout_distance": confirmation_info.breakout_distance if confirmation_info else None,
                "breakout_pct": confirmation_info.breakout_pct if confirmation_info else None,
            },
        )

        self._signal_generated = True
        return signal
