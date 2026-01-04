from src.risk_manager.risk_manager import RiskManager, RiskConfig


def test_can_open_trade_limits():
    rm = RiskManager(RiskConfig(per_trade_pct=1.0, per_day_pct=2.0, max_active_trades=1))
    rm.update_equity(10000.0)
    ok, reason = rm.can_open_trade(stop_distance_pips=10, pip_value_per_lot=10)
    assert ok and reason == "ok"

    rm.register_new_trade("t1", risk_amount_currency=100.0)
    ok, reason = rm.can_open_trade(stop_distance_pips=10, pip_value_per_lot=10)
    assert not ok and reason == "max_active_trades_reached"