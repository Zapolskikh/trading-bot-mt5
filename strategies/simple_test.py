"""
Простая демонстрационная стратегия для тестирования системы.

НЕ ИСПОЛЬЗОВАТЬ В LIVE TRADING - только для тестирования!
"""

from __future__ import annotations
import sys
from pathlib import Path

# Добавляем src в path для импортов (перед другими импортами)
sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import Any, Dict, Optional  # noqa: E402
import logging  # noqa: E402
import pandas as pd  # noqa: E402

from src.common.types import Signal, ExitSignal  # noqa: E402
from src.strategy.strategy import Strategy  # noqa: E402

logger = logging.getLogger(__name__)


class SimpleTestStrategy(Strategy):
    """
    Простейшая тестовая стратегия для проверки работы системы.

    Entry: Всегда возвращает None (не торгует)
    Exit: Всегда возвращает None (полагается на TP/SL)

    Для реальной торговли создайте свою стратегию, наследующую Strategy.
    """

    def entry(self, symbol: str, df: pd.DataFrame) -> Optional[Signal]:
        """
        Не генерирует сигналы - только для тестирования инфраструктуры.
        """
        if df.empty:
            logger.warning(f"[{self.name}] Empty dataframe for {symbol}")
            return None

        logger.info(f"[{self.name}] Checking {symbol}, bars: {len(df)}, last close: {df['close'].iloc[-1]:.5f}")

        # Не торгует - только логирует
        return None

    def exit(self, symbol: str, df: pd.DataFrame, position: Dict[str, Any]) -> Optional[ExitSignal]:
        """
        Не генерирует exit сигналы - полагается на TP/SL.
        """
        return None

    def monitor(self, positions=None):
        """
        Возвращает базовый статус.
        """
        status = super().monitor(positions)
        status["strategy_type"] = "SimpleTestStrategy"
        status["trading"] = False  # Не торгует
        return status
