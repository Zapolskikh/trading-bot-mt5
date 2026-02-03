import pytest
from src.risk_manager.risk_manager import RiskManager, RiskConfig
from src.metatrader_client.client import MetaTraderClient


@pytest.fixture
def mock_mt5_client(mocker):
    """Мок MT5 клиента с предопределенными данными."""
    client = mocker.Mock(spec=MetaTraderClient)
    
    # Мокаем get_symbol_info для EURUSD (5-значная котировка)
    client.get_symbol_info.return_value = {
        "symbol": "EURUSD",
        "digits": 5,
        "point": 0.00001,
        "contract_size": 100000.0,
        "lot_step": 0.01,
        "min_lot": 0.01,
        "max_lot": 100.0,
        "tick_value": 1.0,
        "tick_size": 0.00001,
        "spread": 1.5,
        "ask": 1.10000,
        "bid": 1.09985,
    }
    
    return client


@pytest.fixture
def risk_config():
    """Стандартная конфигурация риска для тестов."""
    return RiskConfig(
        per_trade_pct=1.0,  # 1% риска на сделку
        per_day_pct=3.0,    # 3% дневной риск
        max_active_trades=3,
    )


@pytest.fixture
def risk_manager(risk_config, mock_mt5_client):
    """Инициализированный риск-менеджер."""
    return RiskManager(config=risk_config, mt5_client=mock_mt5_client)


def test_risk_manager_initialization(risk_manager, risk_config):
    """Тест инициализации риск-менеджера."""
    assert risk_manager.config == risk_config
    assert risk_manager.daily_risk_used == 0.0
    assert len(risk_manager.active_trades) == 0


def test_can_open_trade_success(risk_manager):
    """Тест проверки возможности открытия сделки - успешный случай."""
    equity = 10000.0
    can_open, reason = risk_manager.can_open_trade(equity)
    
    assert can_open is True
    assert reason == "ok"


def test_can_open_trade_max_active_reached(risk_manager):
    """Тест проверки - достигнут максимум активных сделок."""
    equity = 10000.0
    
    # Регистрируем максимальное количество сделок
    for i in range(risk_manager.config.max_active_trades):
        risk_manager.register_trade_open(f"trade_{i}", 100.0)
    
    can_open, reason = risk_manager.can_open_trade(equity)
    
    assert can_open is False
    assert reason == "max_active_trades_reached"


def test_can_open_trade_daily_risk_exceeded(risk_manager):
    """Тест проверки - превышен дневной лимит риска."""
    equity = 10000.0
    max_daily_risk = equity * 0.03  # 3% = 300
    
    # Используем весь дневной риск
    risk_manager.daily_risk_used = max_daily_risk
    
    can_open, reason = risk_manager.can_open_trade(equity)
    
    assert can_open is False
    assert reason == "daily_risk_exceeded"


def test_calculate_position_size_basic(risk_manager):
    """Тест расчета размера позиции - базовый случай."""
    symbol = "EURUSD"
    entry_price = 1.10000
    stop_price = 1.09500  # 50 пипов стоп
    equity = 10000.0
    
    lots = risk_manager.calculate_position_size(symbol, entry_price, stop_price, equity)
    
    # Риск = 10000 * 0.01 = 100
    # Стоп = 50 пипов
    # Pip value для EURUSD 1 лот ≈ 10 USD
    # Lots = 100 / (50 * 10) = 0.2
    assert lots > 0
    assert 0.15 <= lots <= 0.25  # Примерно 0.2 с учетом округления


def test_calculate_position_size_small_stop(risk_manager):
    """Тест расчета размера позиции - маленький стоп."""
    symbol = "EURUSD"
    entry_price = 1.10000
    stop_price = 1.09900  # 10 пипов стоп
    equity = 10000.0
    
    lots = risk_manager.calculate_position_size(symbol, entry_price, stop_price, equity)
    
    # С маленьким стопом размер позиции должен быть больше
    # Риск = 100, Стоп = 10 пипов, Pip value ≈ 10
    # Lots = 100 / (10 * 10) = 1.0
    assert lots >= 0.9


def test_calculate_position_size_capped_at_max(risk_manager, mock_mt5_client):
    """Тест расчета размера позиции - ограничение max_lot."""
    # Устанавливаем низкий max_lot
    symbol_info = mock_mt5_client.get_symbol_info.return_value.copy()
    symbol_info["max_lot"] = 0.5
    mock_mt5_client.get_symbol_info.return_value = symbol_info
    
    symbol = "EURUSD"
    entry_price = 1.10000
    stop_price = 1.09990  # Очень маленький стоп = большой размер
    equity = 100000.0  # Большой капитал
    
    lots = risk_manager.calculate_position_size(symbol, entry_price, stop_price, equity)
    
    # Должно быть ограничено max_lot = 0.5
    assert lots <= 0.5


def test_calculate_position_size_below_min_lot(risk_manager):
    """Тест расчета размера позиции - ниже min_lot."""
    symbol = "EURUSD"
    entry_price = 1.10000
    stop_price = 1.09000  # Очень большой стоп = маленький размер
    equity = 1000.0  # Маленький капитал
    
    lots = risk_manager.calculate_position_size(symbol, entry_price, stop_price, equity)
    
    # Если расчетный размер < min_lot (0.01), должно вернуть 0
    assert lots == 0.0


def test_calculate_position_size_invalid_stop(risk_manager):
    """Тест расчета размера позиции - некорректный стоп."""
    symbol = "EURUSD"
    entry_price = 1.10000
    stop_price = 1.10000  # Стоп равен входу
    equity = 10000.0
    
    lots = risk_manager.calculate_position_size(symbol, entry_price, stop_price, equity)
    
    # Должно вернуть 0 при некорректном стопе
    assert lots == 0.0


def test_register_trade_open(risk_manager):
    """Тест регистрации открытия сделки."""
    trade_id = "test_trade_1"
    risk_amount = 100.0
    
    risk_manager.register_trade_open(trade_id, risk_amount)
    
    assert trade_id in risk_manager.active_trades
    assert risk_manager.active_trades[trade_id] == risk_amount
    assert risk_manager.daily_risk_used == risk_amount


def test_register_multiple_trades_open(risk_manager):
    """Тест регистрации нескольких сделок."""
    trades = [("trade_1", 100.0), ("trade_2", 150.0), ("trade_3", 50.0)]
    
    for trade_id, risk in trades:
        risk_manager.register_trade_open(trade_id, risk)
    
    assert len(risk_manager.active_trades) == 3
    assert risk_manager.daily_risk_used == 300.0


def test_register_trade_close(risk_manager):
    """Тест регистрации закрытия сделки."""
    trade_id = "test_trade_1"
    risk_amount = 100.0
    
    # Открываем сделку
    risk_manager.register_trade_open(trade_id, risk_amount)
    assert trade_id in risk_manager.active_trades
    
    # Закрываем сделку
    risk_manager.register_trade_close(trade_id)
    assert trade_id not in risk_manager.active_trades
    # Дневной риск остается использованным
    assert risk_manager.daily_risk_used == risk_amount


def test_register_trade_close_nonexistent(risk_manager):
    """Тест закрытия несуществующей сделки (не должно падать)."""
    risk_manager.register_trade_close("nonexistent_trade")
    
    # Не должно быть ошибок
    assert len(risk_manager.active_trades) == 0


def test_reset_daily_limits(risk_manager):
    """Тест сброса дневных лимитов."""
    # Регистрируем использование
    risk_manager.register_trade_open("trade_1", 100.0)
    assert risk_manager.daily_risk_used > 0
    
    # Сбрасываем
    risk_manager.reset_daily_limits()
    
    assert risk_manager.daily_risk_used == 0.0
    # Активные сделки не должны сбрасываться
    assert len(risk_manager.active_trades) == 1


def test_get_risk_status(risk_manager):
    """Тест получения статуса рисков."""
    equity = 10000.0
    
    # Регистрируем сделку
    risk_manager.register_trade_open("trade_1", 100.0)
    
    status = risk_manager.get_risk_status(equity)
    
    assert status["equity"] == equity
    assert status["max_trade_risk"] == 100.0  # 1% от 10000
    assert status["max_trade_risk_pct"] == 1.0
    assert status["daily_risk_used"] == 100.0
    assert status["daily_risk_limit"] == 300.0  # 3% от 10000
    assert status["daily_risk_pct"] == 3.0
    assert status["daily_risk_remaining"] == 200.0
    assert status["active_trades_count"] == 1
    assert status["max_active_trades"] == 3
    assert status["can_open_new_trade"] is True


def test_get_risk_status_no_trades(risk_manager):
    """Тест статуса рисков без открытых сделок."""
    equity = 10000.0
    
    status = risk_manager.get_risk_status(equity)
    
    assert status["daily_risk_used"] == 0.0
    assert status["daily_risk_remaining"] == 300.0
    assert status["active_trades_count"] == 0
    assert status["can_open_new_trade"] is True


def test_workflow_full_cycle(risk_manager):
    """Интеграционный тест полного цикла работы с рисками."""
    equity = 10000.0
    symbol = "EURUSD"
    
    # 1. Проверяем что можем открыть сделку
    can_open, reason = risk_manager.can_open_trade(equity)
    assert can_open is True
    
    # 2. Рассчитываем размер позиции
    entry_price = 1.10000
    stop_price = 1.09500
    lots = risk_manager.calculate_position_size(symbol, entry_price, stop_price, equity)
    assert lots > 0
    
    # 3. Регистрируем открытие
    trade_id = "workflow_trade_1"
    risk_amount = equity * 0.01  # 1%
    risk_manager.register_trade_open(trade_id, risk_amount)
    
    # 4. Проверяем статус
    status = risk_manager.get_risk_status(equity)
    assert status["active_trades_count"] == 1
    assert status["daily_risk_used"] == risk_amount
    
    # 5. Закрываем сделку
    risk_manager.register_trade_close(trade_id)
    assert trade_id not in risk_manager.active_trades
    
    # 6. Сбрасываем дневные лимиты
    risk_manager.reset_daily_limits()
    assert risk_manager.daily_risk_used == 0.0


@pytest.mark.integration
def test_risk_manager_with_real_mt5_client(mt5_credentials):
    """Интеграционный тест с реальным MT5 клиентом."""
    if not mt5_credentials.get("login"):
        pytest.skip("MT5 credentials not configured")
    
    from src.metatrader_client.client import MetaTraderClient
    
    # Создаем реальный клиент
    client = MetaTraderClient(
        login=mt5_credentials.get("login"),
        password=mt5_credentials.get("password"),
        server=mt5_credentials.get("server"),
    )
    
    try:
        assert client.connect() is True
        
        # Создаем риск-менеджер
        config = RiskConfig(per_trade_pct=1.0, per_day_pct=3.0, max_active_trades=3)
        risk_manager = RiskManager(config=config, mt5_client=client)
        
        # Получаем реальный equity
        portfolio = client.get_portfolio()
        equity = portfolio["equity"]
        assert equity > 0
        
        # Проверяем что можем открыть сделку
        can_open, reason = risk_manager.can_open_trade(equity)
        assert can_open is True
        
        # Рассчитываем размер позиции для реального символа
        symbol = "EURUSD"
        tick = client.get_tick(symbol)
        assert len(tick) > 0
        
        entry_price = tick["ask"]
        stop_price = entry_price - 0.0050  # 50 пипов стоп
        
        lots = risk_manager.calculate_position_size(symbol, entry_price, stop_price, equity)
        assert lots >= 0  # Может быть 0 если слишком маленький капитал
        
        # Проверяем статус
        status = risk_manager.get_risk_status(equity)
        assert status["can_open_new_trade"] is True
        
    finally:
        client.disconnect()

