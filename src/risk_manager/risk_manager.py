from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple, Dict


@dataclass
class RiskConfig:
    per_trade_pct: float
    per_day_pct: float
    max_active_trades: int
    dynamic_enabled: bool = False
    dynamic_rules: Dict = None


class RiskManager:
    """
    Отвечает за:
    - Проверку лимитов (сделка/день/активные)
    - Расчёт размера позиции (лоты)
    - Учёт состояний сделок (new/fill/close)
    TODO: интегрировать pip_value/contract_size через MetaTraderClient.get_symbol_info
    """

    def __init__(self, config: RiskConfig):
        self.config = config
        self.daily_risk_used_currency = 0.0
        self.active_trades: Dict[str, float] = {}  # trade_id -> risk_amount
        self.equity_cache: Optional[float] = None

    def reset_daily_limits(self):
        self.daily_risk_used_currency = 0.0

    def update_equity(self, equity: float):
        self.equity_cache = equity

    def can_open_trade(self, stop_distance_pips: float, pip_value_per_lot: float) -> Tuple[bool, str]:
        if self.equity_cache is None:
            return False, "equity_not_set"
        if len(self.active_trades) >= self.config.max_active_trades:
            return False, "max_active_trades_reached"
        max_daily_risk = self.equity_cache * (self.config.per_day_pct / 100.0)
        if self.daily_risk_used_currency >= max_daily_risk:
            return False, "daily_risk_exceeded"
        if stop_distance_pips <= 0 or pip_value_per_lot <= 0:
            return False, "invalid_stop_or_pip_value"
        return True, "ok"

    def compute_position_size(self, stop_distance_pips: float, pip_value_per_lot: float) -> float:
        """
        lots = risk_amount / (stop_distance_pips * pip_value_per_lot)
        TODO: нормировать по min_lot/lot_step, учитывать тип инструмента
        """
        assert self.equity_cache is not None, "equity_not_set"
        risk_amount = self.equity_cache * (self.config.per_trade_pct / 100.0)
        loss_per_lot = max(1e-12, stop_distance_pips * pip_value_per_lot)
        lots = risk_amount / loss_per_lot
        return max(0.0, lots)

    def register_new_trade(self, trade_id: str, risk_amount_currency: float):
        self.active_trades[trade_id] = risk_amount_currency
        self.daily_risk_used_currency += risk_amount_currency

    def register_close(self, trade_id: str, pnl_currency: float):
        # При закрытии сделки риск освобождается; дневной риск учтён по использованию, pnl влияет на equity вне рамок лимита
        self.active_trades.pop(trade_id, None)