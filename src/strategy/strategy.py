from __future__ import annotations
from typing import Any, Dict, Optional
import pandas as pd
from src.common.types import Signal, ExitSignal


class Strategy:
    """
    Независимая стратегия:
    - prepare_data
    - compute_indicators
    - entry/exit
    - monitor
    - calc_pips
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.last_status: Dict[str, Any] = {}

    def prepare_data(self, symbol: str, timeframe: str, window: int, barsize: str, period: int) -> pd.DataFrame:
        """
        TODO: объединить данные из MetaTraderClient; нормализовать окна
        """
        return pd.DataFrame()

    def compute_indicators(self, df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        """
        TODO: добавить EMA/ATR и др. индикаторы в df
        """
        return df

    def entry(self, symbol: str, df: pd.DataFrame) -> Optional[Signal]:
        """
        TODO: логика входа; вернуть Signal или None
        """
        return None

    def exit(self, symbol: str, df: pd.DataFrame, position: Dict[str, Any]) -> Optional[ExitSignal]:
        """
        TODO: логика выхода; вернуть ExitSignal или None
        """
        return None

    def monitor(self) -> Dict[str, Any]:
        """
        TODO: собрать статус стратегии/индикаторов
        """
        return self.last_status

    def calc_pips(self, symbol: str, price_a: float, price_b: float) -> float:
        """
        TODO: корректный расчёт пипов по info символа
        """
        return abs(price_a - price_b)
