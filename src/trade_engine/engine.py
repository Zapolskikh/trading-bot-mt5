from __future__ import annotations
from typing import Optional
from datetime import datetime

from common.config import load_config
from common.types import Signal
from metatrader_client.client import MetaTraderClient
from risk_manager.risk_manager import RiskManager, RiskConfig
from strategy.strategy import Strategy
from alert_service.telegram import AlertService
from journal_service.csv_journal import JournalService


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
        self.mt = MetaTraderClient(self.config.get("metatrader", {}))
        risk_cfg = self.config.get("risk", {})
        self.risk = RiskManager(
            RiskConfig(
                per_trade_pct=risk_cfg.get("per_trade_pct", 0.5),
                per_day_pct=risk_cfg.get("per_day_pct", 2.0),
                max_active_trades=risk_cfg.get("max_active_trades", 4),
                dynamic_enabled=risk_cfg.get("dynamic", {}).get("enabled", False),
                dynamic_rules=risk_cfg.get("dynamic", {}),
            )
        )
        self.strategy = Strategy(self.config.get("strategy", {}))
        journal_cfg = self.config.get("journal", {})
        self.journal = JournalService(journal_cfg.get("path", "./journal"), journal_cfg.get("rotate_daily", True))
        telegram_cfg = self.config.get("telegram", {})
        self.alerts = AlertService(enabled=telegram_cfg.get("enabled", True))

    def start(self):
        self.mt.connect()

    def poll_and_trade(self):
        """
        TODO: минимальный цикл:
        - получить portfolio/equity
        - получить df → compute_indicators
        - entry → risk → place_order
        - exit → close_position
        - логирование и алерты
        """
        portfolio = self.mt.get_portfolio()
        equity = portfolio.get("equity", 0.0)
        self.risk.update_equity(equity)

        for symbol in self.config["app"]["symbols"]:
            df = self.strategy.prepare_data(
                symbol=symbol,
                timeframe=self.config["app"]["base_timeframe"],
                window=self.config["app"]["data_window"],
                barsize=self.config["app"]["barsize"],
                period=0,
            )
            df = self.strategy.compute_indicators(df, self.config.get("strategy", {}))

            sig: Optional[Signal] = self.strategy.entry(symbol, df)
            if sig:
                # TODO: вычислить стоп в пипах и pip_value_per_lot из symbol_info
                stop_distance_pips = 10.0
                pip_value_per_lot = 10.0
                ok, reason = self.risk.can_open_trade(stop_distance_pips, pip_value_per_lot)
                if not ok:
                    self.alerts.send_risk_alert(f"{symbol} entry blocked: {reason}")
                else:
                    lots = self.risk.compute_position_size(stop_distance_pips, pip_value_per_lot)
                    order_id = self.mt.place_order(
                        symbol=symbol, side=sig.side, lots=lots, sl=sig.sl, tp=sig.tp, type="market", price=sig.price
                    )
                    self.journal.log_order(
                        timestamp=datetime.utcnow().isoformat(),
                        symbol=symbol,
                        side=sig.side,
                        type="market",
                        price=sig.price,
                        lots=lots,
                        sl=sig.sl,
                        tp=sig.tp,
                        status="PLACED",
                        order_id=order_id,
                        trade_id="",
                    )
                    self.alerts.send_signal(sig.__dict__)
                    self.risk.register_new_trade(
                        trade_id=order_id, risk_amount_currency=equity * (self.risk.config.per_trade_pct / 100.0)
                    )

            # TODO: обработка exit сигналов и закрытие позиций

    def reset_daily(self):
        self.risk.reset_daily_limits()
