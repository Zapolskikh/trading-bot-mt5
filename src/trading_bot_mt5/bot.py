import logging
import time
from datetime import datetime

from trading_bot_mt5.client import MetaTraderClient
from trading_bot_mt5.common.config import load_config
from trading_bot_mt5.services.csv_journal import JournalService
from trading_bot_mt5.services.tg_alerts import AlertService
from trading_bot_mt5.strategies.orb.models import ORB_SESSION, RangePeriod, Timeframe
from trading_bot_mt5.strategies.orb.strategy import ConfirmationConfig, ORBConfig, ORBStrategy
from trading_bot_mt5.strategies.orb.visualization import plot_orb_chart

DEBUG = False


class TradeEngine:
    """
    Оркестратор:
    - Получение данных → стратегия → сигналы
    - Риск-проверка → исполнение через MetaTraderClient
    - Журналы + алерты
    - Ежедневные процедуры
    """

    def __init__(self, config_path: str):
        self.config = load_config(config_path)
        mt_cfg = self.config.get("metatrader", {})
        self.mt = MetaTraderClient(
            login=mt_cfg["login"],
            password=mt_cfg["password"],
            server=mt_cfg["server"],
        )

        # ORB strategy setup
        self.orb_config = ORBConfig(
            range_period=RangePeriod.MIN_15,
            range_timeframe=Timeframe.M1,
            session=ORB_SESSION,
            confirmation=ConfirmationConfig(
                require_close=True,
                consecutive_closes=self.config["app"].get("consecutive_closes", 2),
            ),
            risk_reward_target=1.7,
            use_range_stop_loss=True,
            stop_loss_buffer_pct=0.55,
            min_range_size=self.config["app"].get("min_range_size"),
            max_range_size=self.config["app"].get("max_range_size"),
        )
        self.strategy = ORBStrategy(self.orb_config)

        journal_cfg = self.config.get("journal", {})
        self.journal = JournalService(journal_cfg.get("path", "./journal"))
        telegram_cfg = self.config.get("telegram", {})
        self.alerts = AlertService(enabled=telegram_cfg.get("enabled", False))

        self.trading_date = datetime.now()
        self.active_orders: dict = {}

    def start(self) -> bool:
        """Connect to MT5. Returns True if successful."""
        if not self.mt.connect():
            logging.error("[Engine] Failed to connect to MT5")
            return False
        logging.info("[Engine] Connected to MT5")
        return True

    def poll_and_trade(self):
        """
        TODO: минимальный цикл:
        - получить portfolio/equity
        - получить df → compute_indicators
        - entry → risk → place_order
        - exit → close_position
        - логирование и алерты
        """
        logging.info("[Engine] Starting main trading loop")
        while True:
            if self.trading_date.date() != datetime.now().date():
                self.mt.close_all_positions()  # Закрываем все позиции при старте (можно убрать в продакшене)
                self.reset_daily()
                self.trading_date = datetime.now()

            for share in self.config["app"]["shares"]:
                symbol = share["symbol"]
                lots = share["lots"]
                df = self.mt.get_market_data(
                    symbol, self.config["app"]["base_timeframe"], self.config["app"]["data_window"], debug=DEBUG
                )
                signals = self.strategy.process_candles(df, debug=DEBUG)

                if DEBUG:
                    plot_orb_chart(
                        df,
                        opening_range=self.strategy.opening_range,
                        signal=signals[0] if signals else None,
                        title=(
                            f"ORB Strategy - {symbol} Range: {self.orb_config.range_period.value}min Range Size:"
                            f" {self.strategy.opening_range.range_size:.2f} Range Pct:"
                            f" {self.strategy.opening_range.range_pct:.2f}"
                        ),
                        style="yahoo",
                        show_volume=False,
                        show_midpoint=True,
                        save_path=f"output/orb_chart_{symbol}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.png",
                        show=DEBUG,
                    )
                if signals:
                    signal = signals[0]
                    if symbol not in self.active_orders and ORB_SESSION.is_within_session(df.index[-1]):
                        logging.info(
                            f"[Engine] Signal for {symbol}: {signal.signal_type.value} at {signal.entry_price:.2f}"
                        )
                        resp = self.mt.place_order(
                            symbol=symbol,
                            side="buy" if signal.signal_type.value == "LONG" else "sell",
                            volume=lots,
                            sl=signal.stop_loss,
                            tp=signal.take_profit,
                            order_type="limit",
                            price=signal.entry_price,
                        )
                        order_id = str(resp.get("ticket", ""))
                        overall_message = dict(
                            timestamp=datetime.now().isoformat(),
                            symbol=symbol,
                            side="buy" if signal.signal_type.value == "LONG" else "sell",
                            type="limit",
                            price=signal.entry_price,
                            lots=lots,
                            sl=signal.stop_loss,
                            tp=signal.take_profit,
                            sl_dollars=round(abs((signal.entry_price - signal.stop_loss) * lots), 2),
                            tp_dollars=round(abs((signal.take_profit - signal.entry_price) * lots), 2),
                            status="PLACED",
                            order_id=order_id,
                            trade_id="",
                            **self.mt.get_portfolio(),
                        )
                        self.journal.log_order(**overall_message)
                        self.active_orders[symbol] = {order_id: signal}
                        chart = plot_orb_chart(
                            df,
                            opening_range=self.strategy.opening_range,
                            signal=signals[0] if signals else None,
                            title=f"ORB Strategy - {symbol} ({self.orb_config.range_period.value}min Range)",
                            style="yahoo",
                            show_volume=False,
                            show_midpoint=True,
                            save_path=f"output/orb_chart_{symbol}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.png",
                            show=DEBUG,
                            return_bytes=True,
                        )
                        self.alerts.send_chart(chart, overall_message)
                self.strategy.reset()  # Сброс состояния стратегии после обработки сигналов
                time.sleep(10)

        # TODO: обработка exit сигналов и закрытие позиций

    def reset_daily(self):
        self.active_orders.clear()
        logging.info("[Engine] Daily reset completed")


if __name__ == "__main__":
    engine = TradeEngine(config_path="./config/config.yaml")
    if engine.start():
        engine.poll_and_trade()
