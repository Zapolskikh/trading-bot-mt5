from dataclasses import dataclass

import pandas as pd
import pandas_ta as ta


@dataclass(frozen=True, slots=True)
class RangeSizeCalculator:
    """Calculator for determining opening range size relative to ATR."""

    min_multiplier: float = 0.4
    max_multiplier: float = 1.6
    atr_periods: int = 14

    def _calculate_atr(self, candles: pd.DataFrame) -> float:
        """Calculate Average True Range using pandas-ta."""
        if len(candles) < 2:
            return 0.0

        atr_series = ta.atr(high=candles["High"], low=candles["Low"], close=candles["Close"], length=self.atr_periods)
        if atr_series is None or atr_series.empty:
            return 0.0

        last_atr = atr_series.dropna().iloc[-1] if not atr_series.dropna().empty else float("nan")
        return float(last_atr) if pd.notna(last_atr) else 0.0

    def opening_range_allowed(
        self,
        candles: pd.DataFrame,
    ) -> tuple[float | None, float | None]:
        atr = self._calculate_atr(candles)
        if atr == 0:
            return None, None

        min_or = self.min_multiplier * atr
        max_or = self.max_multiplier * atr

        return min_or, max_or
