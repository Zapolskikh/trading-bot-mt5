from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from decimal import Decimal, ROUND_HALF_UP
import logging

if TYPE_CHECKING:
    from trading_bot_mt5.client import MetaTraderClient


@dataclass
class RiskConfig:
    """Конфигурация параметров риска.

    Attributes:
        per_trade_pct: Максимальный риск на сделку в % от equity (например, 1.0 = 1%)
        per_day_pct: Максимальный дневной риск в % от equity (например, 3.0 = 3%)
        max_active_trades: Максимальное количество одновременно открытых сделок
    """

    per_trade_pct: float
    per_day_pct: float
    max_active_trades: int


class RiskManagement:
    """Управление рисками для торговли.

    Отвечает за:
    - Проверку лимитов (риск на сделку, дневной риск, максимум активных сделок)
    - Расчёт размера позиции в лотах на основе риска и стоп-лосса
    - Учёт использованного дневного риска
    - Интеграцию с MetaTraderClient для получения symbol_info
    """

    def __init__(self, config: RiskConfig, mt5_client: MetaTraderClient):
        """Инициализация риск-менеджера.

        Args:
            config: Конфигурация параметров риска
            mt5_client: Клиент для работы с MT5 (для получения symbol_info)
        """
        self.config = config
        self.mt5_client = mt5_client
        self.daily_risk_used = 0.0  # Использованный дневной риск в валюте счета
        self.active_trades: dict[str, float] = {}  # trade_id -> risk_amount

    def reset_daily_limits(self):
        """Сброс дневных лимитов (вызывать в начале каждого торгового дня)."""
        self.daily_risk_used = 0.0
        logging.info("[RiskManagement] Daily limits reset")

    def can_open_trade(self, equity: float) -> tuple[bool, str]:
        """Проверяет возможность открытия новой сделки.

        Args:
            equity: Текущий equity счета

        Returns:
            (можно_открыть, причина)
            - (True, "ok") если все проверки пройдены
            - (False, "reason") с причиной отказа
        """
        # Проверка максимального количества активных сделок
        if len(self.active_trades) >= self.config.max_active_trades:
            return False, "max_active_trades_reached"

        # Проверка дневного лимита риска
        max_daily_risk = equity * (self.config.per_day_pct / 100.0)
        if self.daily_risk_used >= max_daily_risk:
            return False, "daily_risk_exceeded"

        return True, "ok"

    def calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_price: float,
        equity: float,
    ) -> float:
        """Рассчитывает размер позиции в лотах на основе риска.

        Args:
            symbol: Торговый символ (например, "EURUSD")
            entry_price: Цена входа
            stop_price: Цена стоп-лосса
            equity: Текущий equity счета

        Returns:
            Размер позиции в лотах, нормализованный по min_lot/lot_step/max_lot.
            Возвращает 0.0 при ошибке.
        """
        # Рассчитываем максимальный риск на сделку в валюте счета
        risk_amount = equity * (self.config.per_trade_pct / 100.0)

        # Получаем информацию о символе
        symbol_info = self.mt5_client.get_symbol_info(symbol)
        if not symbol_info:
            logging.error(f"[RiskManagement] Failed to get symbol info for {symbol}")
            return 0.0

        # Рассчитываем расстояние до стопа в пипсах
        stop_distance_pips = self._calculate_stop_distance_pips(symbol_info, entry_price, stop_price)

        if stop_distance_pips <= 0:
            logging.error(f"[RiskManagement] Invalid stop distance: {stop_distance_pips}")
            return 0.0

        # Рассчитываем pip value для 1 лота
        pip_value = self._calculate_pip_value(symbol_info, lots=1.0)

        if pip_value <= 0:
            logging.error(f"[RiskManagement] Invalid pip value: {pip_value}")
            return 0.0

        # Рассчитываем размер позиции: lots = risk / (stop_distance * pip_value)
        loss_per_lot = stop_distance_pips * pip_value
        lots = risk_amount / loss_per_lot

        # Нормализуем размер позиции
        lots = self._normalize_volume(lots, symbol_info)

        logging.info(
            f"[RiskManagement] Position size: {lots:.2f} lots for {symbol}, "
            f"risk={risk_amount:.2f}, stop_distance={stop_distance_pips:.1f} pips, "
            f"pip_value={pip_value:.2f}"
        )

        return lots

    def register_trade_open(self, trade_id: str, risk_amount: float):
        """Регистрирует открытие новой сделки.

        Args:
            trade_id: Уникальный идентификатор сделки
            risk_amount: Риск сделки в валюте счета
        """
        self.active_trades[trade_id] = risk_amount
        self.daily_risk_used += risk_amount
        logging.info(
            f"[RiskManagement] Trade {trade_id} opened, risk={risk_amount:.2f}, "
            f"daily_used={self.daily_risk_used:.2f}, active_trades={len(self.active_trades)}"
        )

    def register_trade_close(self, trade_id: str):
        """Регистрирует закрытие сделки.

        Args:
            trade_id: Уникальный идентификатор сделки
        """
        risk_amount = self.active_trades.pop(trade_id, 0.0)
        logging.info(
            f"[RiskManagement] Trade {trade_id} closed, risk was {risk_amount:.2f}, "
            f"active_trades={len(self.active_trades)}"
        )

    def get_risk_status(self, equity: float) -> dict[str, Any]:
        """Возвращает текущий статус рисков.

        Args:
            equity: Текущий equity счета

        Returns:
            Словарь с информацией о рисках
        """
        max_daily_risk = equity * (self.config.per_day_pct / 100.0)
        max_trade_risk = equity * (self.config.per_trade_pct / 100.0)

        return {
            "equity": equity,
            "max_trade_risk": max_trade_risk,
            "max_trade_risk_pct": self.config.per_trade_pct,
            "daily_risk_used": self.daily_risk_used,
            "daily_risk_limit": max_daily_risk,
            "daily_risk_pct": self.config.per_day_pct,
            "daily_risk_remaining": max_daily_risk - self.daily_risk_used,
            "active_trades_count": len(self.active_trades),
            "max_active_trades": self.config.max_active_trades,
            "can_open_new_trade": self.can_open_trade(equity)[0],
        }

    def _calculate_stop_distance_pips(self, symbol_info: dict, entry_price: float, stop_price: float) -> float:
        """Рассчитывает расстояние до стопа в пипсах."""
        price_distance = abs(entry_price - stop_price)

        # Для 5-значных котировок (EURUSD: 1.12345) 1 пип = 10 поинтов
        # Для 3-значных (USDJPY: 123.45) 1 пип = 1 поинт
        digits = symbol_info["digits"]
        pip_multiplier = 10 if digits == 5 or digits == 3 else 1

        pips = (price_distance / symbol_info["point"]) / pip_multiplier
        return pips

    def _calculate_pip_value(self, symbol_info: dict, lots: float = 1.0) -> float:
        """Рассчитывает стоимость 1 пипа для указанного объема.

        pip_value = (tick_value / tick_size) * point * pip_multiplier * lots
        """
        digits = symbol_info["digits"]
        pip_multiplier = 10 if digits == 5 or digits == 3 else 1

        tick_value = symbol_info["tick_value"]
        tick_size = symbol_info["tick_size"]
        point = symbol_info["point"]

        # pip_value на 1 лот
        pip_value = (tick_value / tick_size) * point * pip_multiplier * lots
        return pip_value

    def _normalize_volume(self, lots: float, symbol_info: dict) -> float:
        """Нормализует объем по min_lot, max_lot и lot_step."""
        min_lot = symbol_info["min_lot"]
        max_lot = symbol_info["max_lot"]
        lot_step = symbol_info["lot_step"]

        # Округляем до lot_step
        v = Decimal(str(lots))
        s = Decimal(str(lot_step))
        if s > 0:
            q = (v / s).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            lots = float(q * s)

        # Ограничиваем min/max
        if lots < min_lot:
            logging.warning(f"[RiskManagement] Volume {lots} below min_lot {min_lot}, returning 0")
            return 0.0

        if lots > max_lot:
            logging.warning(f"[RiskManagement] Volume {lots} exceeds max_lot {max_lot}, capping to {max_lot}")
            lots = max_lot

        return lots
