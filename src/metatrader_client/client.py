from __future__ import annotations
from typing import Any, Dict, List, Optional
import pandas as pd


class MetaTraderClient:
    """
    Большой класс-обёртка над MetaTrader (MT5 предпочтительно).
    Ответственность:
    - Подключение
    - Данные (тик/бар)
    - Торговые операции
    - Позиции/ордера/история
    - Аналитика портфеля
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.connected = False

    def connect(self) -> bool:
        """
        TODO: реализация подключения к терминалу (через MT5 API)
        """
        self.connected = True
        return self.connected

    def disconnect(self):
        self.connected = False

    def get_market_data(self, symbol: str, timeframe: str, window: int) -> pd.DataFrame:
        """
        TODO: вернуть DataFrame с колонками: time, open, high, low, close, volume
        """
        return pd.DataFrame()

    def get_tick(self, symbol: str) -> Dict[str, Any]:
        """
        TODO: вернуть последний тик: bid/ask/last/time
        """
        return {}

    def place_order(
        self,
        symbol: str,
        side: str,
        lots: float,
        sl: Optional[float],
        tp: Optional[float],
        type: str = "market",
        price: Optional[float] = None,
    ) -> str:
        """
        TODO: отправить заявку и вернуть order_id; обеспечить идемпотентность
        """
        return "order_0001"

    def modify_order(self, order_id: str, sl: Optional[float] = None, tp: Optional[float] = None):
        """
        TODO: изменить параметры заявки
        """
        return True

    def close_position(self, position_id: str, lots: Optional[float] = None) -> str:
        """
        TODO: закрыть позицию (полностью/частично) и вернуть deal_id
        """
        return "deal_0001"

    def get_positions(self) -> List[Dict[str, Any]]:
        return []

    def get_orders(self) -> List[Dict[str, Any]]:
        return []

    def get_history(self, since: Optional[str] = None, until: Optional[str] = None) -> List[Dict[str, Any]]:
        return []

    def get_portfolio(self) -> Dict[str, Any]:
        """
        TODO: вернуть баланс/эквити/маржу
        """
        return {"balance": 0.0, "equity": 0.0, "margin": 0.0, "free_margin": 0.0}

    def get_symbol_info(self, symbol: str) -> Dict[str, Any]:
        """
        TODO: вернуть параметры символа: digits, point, contract_size, lot_step, min_lot, tick_value/tick_size
        """
        return {"digits": 5, "point": 0.00001, "contract_size": 100000, "lot_step": 0.01, "min_lot": 0.01}
