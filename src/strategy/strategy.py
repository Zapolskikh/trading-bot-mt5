from __future__ import annotations
from typing import Any, Dict, Optional, List
import logging
import pandas as pd
from src.common.types import Signal, ExitSignal
from src.metatrader_client.client import MetaTraderClient

logger = logging.getLogger(__name__)


class Strategy:
    """
    Базовый класс стратегии - гибкий интерфейс для любых типов торговли:
    - Индикаторные стратегии (маркет ордера)
    - Уровневые стратегии (лимитные ордера)
    - Новостные стратегии (внешние API)
    - Комбинированные подходы

    Обязательные методы для переопределения:
    - entry() - логика поиска входа

    Опциональные методы:
    - prepare_data() - получение и форматирование данных
    - compute_indicators() - расчет индикаторов
    - exit() - логика выхода
    - monitor() - мониторинг открытых позиций
    """

    def __init__(self, config: Dict[str, Any], mt5_client: MetaTraderClient):
        """
        Args:
            config: Конфигурация стратегии из config.yaml
            mt5_client: Клиент для работы с MT5
        """
        self.config = config
        self.mt5_client = mt5_client
        self.name = config.get("name", self.__class__.__name__)
        self.symbols = config.get("symbols", [])
        self.timeframe = config.get("timeframe", "H1")
        self.last_status: Dict[str, Any] = {}

        logger.info(f"[{self.name}] Strategy initialized: {self.symbols} on {self.timeframe}")

    def prepare_data(self, symbol: str, timeframe: Optional[str] = None, window: int = 100) -> pd.DataFrame:
        """
        Получение рыночных данных через MT5 client.

        Базовая реализация - простое получение OHLCV баров.
        Переопределите для:
        - Специфического форматирования данных
        - Получения данных из внешних API (новости, sentiment)
        - Объединения нескольких таймфреймов

        Args:
            symbol: Торговый инструмент
            timeframe: Таймфрейм (если None, использует self.timeframe)
            window: Количество баров

        Returns:
            DataFrame с колонками: time, open, high, low, close, volume
        """
        tf = timeframe or self.timeframe

        try:
            df = self.mt5_client.get_market_data(symbol=symbol, timeframe=tf, window=window)

            if not df.empty:
                logger.debug(f"[{self.name}] Loaded {len(df)} bars for {symbol} {tf}")
                return df
            else:
                logger.error(f"[{self.name}] Failed to load data for {symbol}")
                return pd.DataFrame()

        except Exception as e:
            logger.error(f"[{self.name}] Error in prepare_data: {e}")
            return pd.DataFrame()

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Расчет технических индикаторов.

        Базовая реализация - возвращает df без изменений.
        Переопределите для добавления индикаторов (EMA, RSI, ATR и т.д.)

        Args:
            df: DataFrame с OHLCV данными

        Returns:
            DataFrame с добавленными колонками индикаторов

        Example:
            ```python
            def compute_indicators(self, df):
                df["ema_9"] = ta.ema(df["close"], 9)
                df["atr"] = ta.atr(df["high"], df["low"], df["close"], 14)
                return df
            ```
        """
        return df

    def entry(self, symbol: str, df: pd.DataFrame) -> Optional[Signal]:
        """
        Логика поиска точки входа в рынок.

        ОБЯЗАТЕЛЬНО переопределить в наследнике!

        Типы стратегий:
        1. Индикаторные (маркет ордера):
           - Анализ пересечений, дивергенций
           - Возврат Signal с side="buy"/"sell", price=текущая цена

        2. Уровневые (лимитные ордера):
           - Поиск зон поддержки/сопротивления
           - Возврат Signal с side="buy_limit"/"sell_limit", price=уровень

        3. Новостные:
           - Проверка календаря через API
           - Возврат Signal перед важным событием

        Args:
            symbol: Торговый инструмент
            df: DataFrame с данными и индикаторами

        Returns:
            Signal если найдена точка входа, иначе None

        Example:
            ```python
            if df["ema_9"].iloc[-1] > df["ema_21"].iloc[-1]:
                return Signal(
                    symbol=symbol,
                    side="buy",
                    price=df["close"].iloc[-1],
                    sl=df["close"].iloc[-1] - atr * 2,
                    tp=df["close"].iloc[-1] + atr * 3,
                    confidence=0.8,
                )
            ```
        """
        raise NotImplementedError(f"{self.__class__.__name__} must implement entry() method")

    def exit(self, symbol: str, df: pd.DataFrame, position: Dict[str, Any]) -> Optional[ExitSignal]:
        """
        Логика выхода из позиции.

        Опциональный метод - можно полагаться только на TP/SL.
        Переопределите для:
        - Динамических условий выхода
        - Обратных сигналов индикаторов
        - Выхода по времени
        - Частичного закрытия позиций

        Args:
            symbol: Торговый инструмент
            df: Актуальные данные с индикаторами
            position: Информация о позиции (ticket, side, entry_price, open_time и т.д.)

        Returns:
            ExitSignal если нужно выйти, иначе None

        Example:
            ```python
            # Выход при обратном кроссовере
            if position["side"] == "buy" and df["ema_9"].iloc[-1] < df["ema_21"].iloc[-1]:
                return ExitSignal(symbol=symbol, action="close", reason="reverse_signal")
            ```
        """
        return None  # По умолчанию полагаемся на TP/SL

    def monitor(self, positions: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Мониторинг открытых позиций и состояния стратегии.

        Опциональный метод для:
        - Обновления trailing stops
        - Перемещения SL в breakeven
        - Частичного закрытия позиций
        - Логирования состояния

        Args:
            positions: Список открытых позиций стратегии

        Returns:
            Словарь со статусом стратегии (для логов/дашборда)

        Example:
            ```python
            def monitor(self, positions):
                for pos in positions or []:
                    # Переместить в breakeven после 20 пипов прибыли
                    profit_pips = (pos["current_price"] - pos["entry_price"]) * 10000
                    if profit_pips > 20 and pos["sl"] < pos["entry_price"]:
                        self.mt5_client.modify_position(ticket=pos["ticket"], sl=pos["entry_price"])

                return {"active_positions": len(positions or [])}
            ```
        """
        return {
            "name": self.name,
            "symbols": self.symbols,
            "timeframe": self.timeframe,
            "active_positions": len(positions or []),
        }

    def calc_pips(self, symbol: str, price_a: float, price_b: float) -> float:
        """
        Расчет разницы в пипсах между двумя ценами.

        TODO: Добавить корректный расчёт с учетом digits символа из symbol_info

        Args:
            symbol: Торговый инструмент
            price_a: Первая цена
            price_b: Вторая цена

        Returns:
            Разница в пипсах
        """
        return abs(price_a - price_b)
