"""
Основной процесс торгового бота.

Отвечает за:
- Инициализацию MT5 клиента
- Загрузку и инициализацию стратегии
- Основной торговый цикл (entry → monitor → exit)
- Управление жизненным циклом сделок
"""

from __future__ import annotations
import logging
import time
import importlib.util
import sys
from pathlib import Path
from typing import Optional, Any
from datetime import datetime

from src.common.config import load_config
from src.metatrader_client.client import MetaTraderClient
from src.risk_manager.risk_manager import RiskManager, RiskConfig
from src.alert_service.telegram import AlertService
from src.journal_service.csv_journal import JournalService

logger = logging.getLogger(__name__)


class TradingBot:
    """
    Основной класс торгового бота.

    Управляет полным циклом торговли:
    1. Инициализация компонентов (MT5, Risk, Alerts, Journal)
    2. Загрузка стратегии из strategies/
    3. Основной цикл: entry → monitor → exit
    """

    def __init__(self, config_path: str):
        """
        Args:
            config_path: Путь к YAML конфигу
        """
        logger.info("=== Initializing Trading Bot ===")

        # Загрузка конфига
        self.config = load_config(config_path)

        # Инициализация MT5 клиента
        mt_cfg = self.config.get("metatrader", {})
        self.mt5_client = MetaTraderClient(
            login=mt_cfg["login"],
            password=mt_cfg["password"],
            server=mt_cfg["server"],
        )

        # Инициализация Risk Manager
        risk_cfg = self.config.get("risk", {})
        self.risk_manager = RiskManager(
            config=RiskConfig(
                per_trade_pct=risk_cfg.get("per_trade_pct", 1.0),
                per_day_pct=risk_cfg.get("per_day_pct", 3.0),
                max_active_trades=risk_cfg.get("max_active_trades", 2),
            ),
            mt5_client=self.mt5_client,
        )

        # Инициализация Alert Service
        telegram_cfg = self.config.get("telegram", {})
        self.alert_service = AlertService(enabled=telegram_cfg.get("enabled", True))

        # Инициализация Journal
        journal_cfg = self.config.get("journal", {})
        self.journal = JournalService(journal_cfg.get("path", "./journal"), journal_cfg.get("rotate_daily", True))

        # Стратегия (загружается отдельно)
        self.strategy = None

        # Отслеживание открытых сделок
        self.active_trades: dict[int, dict[str, Any]] = {}  # ticket -> {symbol, entry_time, entry_price, ...}

        logger.info("Trading Bot initialized")

    def connect(self) -> bool:
        """Подключение к MT5"""
        if not self.mt5_client.connect():
            logger.error("Failed to connect to MT5")
            return False

        logger.info("✓ Connected to MT5")
        return True

    def load_strategy(self, strategy_name: str):
        """
        Динамическая загрузка стратегии из strategies/

        Args:
            strategy_name: Имя файла стратегии без .py (например, 'simple_test')
        """
        strategy_path = Path("strategies") / f"{strategy_name}.py"

        if not strategy_path.exists():
            raise FileNotFoundError(f"Strategy file not found: {strategy_path}")

        # Динамический импорт
        spec = importlib.util.spec_from_file_location(strategy_name, strategy_path)
        if spec is None or spec.loader is None:
            raise ValueError(f"Failed to load spec for {strategy_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[strategy_name] = module
        spec.loader.exec_module(module)

        # Найти класс Strategy в модуле
        strategy_class = None
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type) and attr.__module__ == strategy_name and attr_name != "Strategy"
            ):  # Не базовый класс
                strategy_class = attr
                break

        if not strategy_class:
            raise ValueError(f"No Strategy class found in {strategy_path}")

        # Инициализация стратегии
        self.strategy = strategy_class(config=self.config.get("strategy", {}), mt5_client=self.mt5_client)

        if self.strategy:
            logger.info(f"✓ Strategy loaded: {self.strategy.name} ({strategy_class.__name__})")

    def _cleanup_closed_trade(self, ticket: int):
        """Очистка закрытой сделки из активных"""
        if ticket in self.active_trades:
            del self.active_trades[ticket]
            self.risk_manager.register_trade_close(trade_id=str(ticket))

    def run_cycle(self):
        """
        Один цикл торговли - УНИВЕРСАЛЬНЫЙ ЭКЗЕКЬЮТОР.

        1. Для каждого символа вызывает strategy.entry()
        2. Если есть сигнал - проверяет риск и открывает позицию
        3. Для активных позиций проверяет strategy.exit()
        4. Вызывает strategy.monitor() для мониторинга
        """
        symbols = self.config.get("app", {}).get("symbols", [])

        # === 1. ENTRY: Проверка новых входов ===
        for symbol in symbols:
            # Пропустить если уже есть открытая позиция по символу
            if any(t["symbol"] == symbol for t in self.active_trades.values()):
                continue

            # Получить данные и индикаторы
            df = self.strategy.prepare_data(symbol)
            if df.empty:
                logger.debug(f"Empty data for {symbol}")
                continue

            df = self.strategy.compute_indicators(df)

            # Вызвать strategy.entry() - ЛОГИКА СТРАТЕГИИ
            signal = self.strategy.entry(symbol, df)
            if not signal:
                continue

            logger.info(f"📊 Entry signal from strategy: {symbol} {signal.side} @ {signal.price:.5f}")

            # Проверить риск-менеджмент
            portfolio = self.mt5_client.get_portfolio()
            equity = portfolio.get("equity", 0.0)

            ok, reason = self.risk_manager.can_open_trade(equity)
            if not ok:
                logger.warning(f"❌ Entry blocked: {reason}")
                self.alert_service.send_risk_alert(f"{symbol} entry blocked: {reason}")
                continue

            # Рассчитать размер позиции
            lots = self.risk_manager.calculate_position_size(
                symbol=symbol, entry_price=signal.price, stop_price=signal.sl, equity=equity
            )

            if lots <= 0:
                logger.warning("❌ Calculated lot size is 0")
                continue

            # Открыть позицию
            result = self.mt5_client.place_order(
                symbol=symbol,
                side=signal.side,
                volume=lots,
                sl=signal.sl,
                tp=signal.tp,
                order_type="market",
                price=signal.price,
                volume_currency="lots",
            )

            if not result.get("success"):
                logger.error(f"❌ Failed to place order: {result.get('error')}")
                continue

            ticket = result.get("ticket")
            logger.info(f"✅ Position opened: #{ticket} {symbol} {signal.side} {lots} lots")

            # Зарегистрировать сделку
            risk_amount = abs(signal.price - signal.sl) * lots
            self.risk_manager.register_trade_open(trade_id=str(ticket), risk_amount=risk_amount)

            # Сохранить в активные сделки
            trade_info = {
                "ticket": ticket,
                "symbol": symbol,
                "side": signal.side,
                "entry_price": signal.price,
                "lots": lots,
                "sl": signal.sl,
                "tp": signal.tp,
                "entry_time": datetime.now(),
            }
            self.active_trades[ticket] = trade_info

            # Логирование и алерты
            self.journal.log_order(
                timestamp=datetime.utcnow().isoformat(),
                symbol=symbol,
                side=signal.side,
                type="market",
                price=signal.price,
                lots=lots,
                sl=signal.sl,
                tp=signal.tp,
                status="FILLED",
                order_id=str(ticket),
                trade_id=str(ticket),
            )
            self.alert_service.send_signal(signal.__dict__)

            # Только одна позиция за цикл
            break

        # === 2. MONITOR & EXIT: Обработка активных позиций ===
        positions = self.mt5_client.get_positions()

        for ticket in list(self.active_trades.keys()):
            trade_info = self.active_trades[ticket]
            symbol = trade_info["symbol"]

            # Проверить что позиция все еще открыта
            position = next((p for p in positions if p.get("ticket") == ticket), None)

            if not position:
                logger.info(f"Position #{ticket} closed (TP/SL hit)")
                self._cleanup_closed_trade(ticket)
                continue

            # Получить свежие данные
            df = self.strategy.prepare_data(symbol)
            if df.empty:
                continue

            df = self.strategy.compute_indicators(df)

            # Вызвать strategy.exit() - ЛОГИКА СТРАТЕГИИ
            exit_signal = self.strategy.exit(symbol, df, position)

            if exit_signal:
                logger.info(f"🚪 Exit signal from strategy: {symbol} - {exit_signal.reason}")

                # Закрыть позицию
                result = self.mt5_client.close_position(
                    ticket=ticket, lots=exit_signal.lots if exit_signal.action == "partial" else None
                )

                if result.get("success"):
                    logger.info(f"✅ Position closed: #{ticket} - {exit_signal.reason}")
                    self._cleanup_closed_trade(ticket)
                    self.alert_service.send_trade_closed(position, exit_signal.reason)
                else:
                    logger.error(f"❌ Failed to close position: {result.get('error')}")

        # === 3. MONITOR: Вызвать strategy.monitor() ===
        if self.active_trades and hasattr(self.strategy, "monitor"):
            self.strategy.monitor(list(self.active_trades.values()))

    def run(self, cycles: Optional[int] = None, interval: int = 5):
        """
        Основной торговый цикл.

        Args:
            cycles: Количество циклов (None = бесконечно)
            interval: Интервал между циклами в секундах
        """
        logger.info(f"🚀 Starting trading loop (interval={interval}s)")

        cycle_count = 0
        try:
            while True:
                cycle_count += 1
                logger.info(f"--- Cycle {cycle_count} ---")

                self.run_cycle()

                # Статус
                logger.info(f"Active trades: {len(self.active_trades)}")

                if cycles and cycle_count >= cycles:
                    logger.info(f"Completed {cycles} cycles")
                    break

                time.sleep(interval)

        except KeyboardInterrupt:
            logger.info("Bot stopped by user")

        finally:
            self.shutdown()

    def shutdown(self):
        """Корректное завершение работы"""
        logger.info("=== Shutting down ===")

        # Закрыть все активные позиции (опционально)
        if self.active_trades:
            logger.warning(f"{len(self.active_trades)} active trades remain open")

        # Отключиться от MT5
        self.mt5_client.shutdown()

        logger.info("Bot shutdown complete")

    def reset_daily(self):
        """Сброс дневных лимитов"""
        self.risk_manager.reset_daily_limits()
        logger.info("Daily limits reset")


def main(config_path: str, strategy_name: str, cycles: Optional[int] = None):
    """
    Главная функция запуска бота.

    Args:
        config_path: Путь к конфигу
        strategy_name: Имя стратегии из strategies/
        cycles: Количество циклов (None = бесконечно)
    """
    # Настройка логирования
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # Создание и инициализация бота
    bot = TradingBot(config_path)

    # Подключение к MT5
    if not bot.connect():
        logger.error("Failed to connect to MT5")
        return

    # Загрузка стратегии
    try:
        bot.load_strategy(strategy_name)
    except Exception as e:
        logger.error(f"Failed to load strategy '{strategy_name}': {e}")
        return

    # Запуск основного цикла
    bot.run(cycles=cycles, interval=5)
