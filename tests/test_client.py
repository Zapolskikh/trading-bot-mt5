import pytest
from trading_bot_mt5.client import MetaTraderClient


@pytest.mark.integration
def test_currency_to_lots_conversion(mt5_credentials):
    """Тест конвертации валют в лоты через currency_to_lots метод.

    Проверяет:
    - Конвертация USD в лоты
    - Конвертация EUR в лоты (через EURUSD курс)
    - Валидация минимального размера лота
    - Округление по lot_step
    - Обработка неподдерживаемых валют
    """
    if not mt5_credentials.get("login"):
        pytest.skip("MT5 credentials not configured")

    client = client_mod.MetaTraderClient(
        login=mt5_credentials.get("login"),
        password=mt5_credentials.get("password"),
        server=mt5_credentials.get("server"),
    )
    symbol = "EURUSD"

    try:
        assert client.connect() is True

        # Test USD conversion
        lots_from_usd = client.currency_to_lots(amount=10000.0, currency="USD", symbol=symbol)
        assert lots_from_usd > 0, "USD conversion should return positive lots"
        assert lots_from_usd == pytest.approx(0.1, abs=0.01), "10k USD should be ~0.1 lots for EURUSD"

        # Test EUR conversion
        lots_from_eur = client.currency_to_lots(amount=10000.0, currency="EUR", symbol=symbol)
        assert lots_from_eur > 0, "EUR conversion should return positive lots"
        # EUR conversion depends on EURUSD rate, should be close to USD result
        assert 0.05 < lots_from_eur < 0.15, "EUR conversion should yield reasonable lot size"

        # Test small amount (below min_lot)
        lots_small = client.currency_to_lots(amount=100.0, currency="USD", symbol=symbol)
        assert lots_small == 0, "Amount below min_lot should return 0"

        # Test unsupported currency
        lots_invalid = client.currency_to_lots(amount=1000.0, currency="GBP", symbol=symbol)
        assert lots_invalid == 0, "Unsupported currency should return 0"

        # Test case insensitivity
        lots_lowercase = client.currency_to_lots(amount=5000.0, currency="usd", symbol=symbol)
        lots_uppercase = client.currency_to_lots(amount=5000.0, currency="USD", symbol=symbol)
        assert lots_lowercase == lots_uppercase, "Currency parameter should be case-insensitive"

    finally:
        client.disconnect()


@pytest.mark.integration
def test_mt5_connection_workflow(mt5_credentials):
    """Интеграционный тест полного цикла работы MT5 клиента.

    Тест берет данные для подключения из переменных окружения .env:
    - MT5_LOGIN
    - MT5_PASSWORD
    - MT5_SERVER

     Проверяемые этапы:
     1. Подключение:
        - Успешное подключение к MT5 терминалу (connect() returns bool)
        - Проверка работоспособности через get_tick()

     2. Получение рыночных данных:
        - Загрузка исторических данных (OHLCV bars) через get_market_data()
        - Проверка структуры DataFrame (наличие колонок, индекс по времени)
        - Получение текущей цены (bid/ask/spread) через get_tick()

     3. Выставление лимитного ордера:
        - Создание BUY LIMIT ордера через place_order()
        - Проверка успешности выставления (success flag, ticket > 0)
        - Получение списка активных ордеров через get_orders()
        - Проверка наличия ордера в списке с корректными параметрами

     4. Модификация ордера:
        - Изменение цены ордера через modify_order()
        - Установка Stop Loss и Take Profit
        - Проверка что старые и новые значения отличаются
        - Проверка отражения изменений в get_orders()

     5. Отмена ордера:
        - Удаление ордера из очереди через cancel_order()
        - Проверка успешности отмены
        - Проверка что ордер удален из get_orders()

     6. Отключение:
        - Закрытие соединения через disconnect()
    """

    if not mt5_credentials.get("login"):
        pytest.skip("MT5 credentials not configured")

    # Setup
    client = MetaTraderClient(
        login=mt5_credentials.get("login"),
        password=mt5_credentials.get("password"),
        server=mt5_credentials.get("server"),
    )
    symbol = "USDCHF"
    order_amount_usd = 1000.0

    try:
        # 1. Подключение
        assert client.connect() is True

        # Verify connection by calling get_tick (get_portfolio is TODO stub)
        tick_test = client.get_tick("EURUSD")
        assert len(tick_test) > 0, "Should be able to get tick after connect"
        assert "bid" in tick_test and "ask" in tick_test, "Tick should have bid/ask"

        # 2. Рыночные данные и текущий тик
        df = client.get_market_data(symbol="EURUSD", timeframe="H1", window=10)
        assert len(df) > 0, "Market data should return bars"
        assert all(col in df.columns for col in ["open", "high", "low", "close", "tick_volume"])
        assert df.index.name == "time", "DataFrame index should be 'time'"

        tick_eurusd = client.get_tick(symbol="EURUSD")
        assert len(tick_eurusd) > 0, "Tick should return data"
        assert all(k in tick_eurusd for k in ["bid", "ask", "spread", "volume"])
        assert tick_eurusd["ask"] >= tick_eurusd["bid"], "Ask should be >= bid"

        # 3. Order Operations: Place → Get → Modify → Cancel
        tick_order = client.get_tick(symbol=symbol)
        assert len(tick_order) > 0, f"Tick for {symbol} should return data"

        limit_price = tick_order["bid"] - 0.001
        assert limit_price > 0, "Limit price should be positive"

        # Place limit order (using currency_to_lots converter)
        volume_lots = client.currency_to_lots(amount=order_amount_usd, currency="USD", symbol=symbol)
        assert volume_lots > 0, "Currency conversion should return valid lot size"

        order_result = client.place_order(
            symbol=symbol,
            side="buy",
            volume=volume_lots,
            order_type="limit",
            price=limit_price,
            volume_currency="lots",
        )
        assert order_result["success"], f"Order placement failed: {order_result['comment']}"
        assert order_result["ticket"] > 0, "Order ticket should be positive"
        order_ticket = order_result["ticket"]

        # Verify order in active orders
        orders = client.get_orders()
        assert len(orders) > 0, "Should have at least one active order"
        placed_order = next((o for o in orders if o["ticket"] == order_ticket), None)
        assert placed_order is not None, f"Order {order_ticket} should be in active orders"
        assert placed_order["symbol"] == symbol, f"Order symbol should be {symbol}"
        assert placed_order["type"] == "buy_limit", "Order type should be buy_limit"
        assert placed_order["volume"] > 0, "Order volume should be positive"
        assert abs(placed_order["price"] - limit_price) < 0.00001, "Order price should match limit price"

        # Modify order (adjust price and add SL/TP)
        new_price = limit_price + 0.0005
        modify_result = client.modify_order(
            order_id=order_ticket, price=new_price, sl=new_price - 0.001, tp=new_price + 0.002
        )
        assert modify_result["success"], f"Order modification failed: {modify_result['comment']}"
        assert modify_result["old_values"]["price"] != new_price, "Price should have changed"
        assert abs(modify_result["new_values"]["price"] - new_price) < 0.00001, "New price should be set"

        # Verify modification via get_orders()
        orders_after_modify = client.get_orders()
        modified_order = next((o for o in orders_after_modify if o["ticket"] == order_ticket), None)
        assert modified_order is not None, f"Modified order {order_ticket} should still exist"
        assert abs(modified_order["price"] - new_price) < 0.00001, "Modified price should be reflected"

        # Cancel order
        cancel_result = client.cancel_order(order_id=order_ticket)
        assert cancel_result["success"], f"Order cancellation failed: {cancel_result['comment']}"
        assert cancel_result["ticket"] == order_ticket, "Canceled ticket should match"

        # Verify cancellation via get_orders()
        final_orders = client.get_orders()
        remaining = next((o for o in final_orders if o["ticket"] == order_ticket), None)
        assert remaining is None, f"Order {order_ticket} should be removed after cancellation"

    finally:
        # Cleanup
        client.disconnect()

@pytest.mark.integration
def test_get_positions_and_portfolio(mt5_credentials):
    """Тест получения открытых позиций и данных портфеля.

    Проверяет:
    - Получение списка всех позиций через get_positions()
    - Фильтрация позиций по символу
    - Получение метрик портфеля через get_portfolio()
    - Структуру возвращаемых данных
    """
    if not mt5_credentials.get("login"):
        pytest.skip("MT5 credentials not configured")

    client = client_mod.MetaTraderClient(
        login=mt5_credentials.get("login"),
        password=mt5_credentials.get("password"),
        server=mt5_credentials.get("server"),
    )

    try:
        assert client.connect() is True

        # Test get_positions (all)
        all_positions = client.get_positions()
        assert isinstance(all_positions, list), "get_positions should return list"
        
        # Test get_positions (filtered by symbol)
        eurusd_positions = client.get_positions(symbol="EURUSD")
        assert isinstance(eurusd_positions, list), "get_positions(symbol) should return list"
        
        # If there are any EURUSD positions, verify structure
        if len(eurusd_positions) > 0:
            pos = eurusd_positions[0]
            assert "ticket" in pos and pos["ticket"] > 0
            assert "symbol" in pos and pos["symbol"] == "EURUSD"
            assert "type" in pos and pos["type"] in ["buy", "sell"]
            assert "volume" in pos and pos["volume"] > 0
            assert "price_open" in pos
            assert "profit" in pos
            assert "sl" in pos and "tp" in pos

        # Test get_portfolio
        portfolio = client.get_portfolio()
        assert isinstance(portfolio, dict), "get_portfolio should return dict"
        assert "balance" in portfolio and portfolio["balance"] >= 0
        assert "equity" in portfolio and portfolio["equity"] >= 0
        assert "margin" in portfolio and portfolio["margin"] >= 0
        assert "margin_level" in portfolio
        assert "currency" in portfolio and len(portfolio["currency"]) > 0
        assert "leverage" in portfolio and portfolio["leverage"] > 0
        assert "trade_mode" in portfolio and portfolio["trade_mode"] in ["demo", "contest", "real"]

    finally:
        client.disconnect()


@pytest.mark.integration
def test_get_history(mt5_credentials):
    """Тест получения торговой истории.

    Проверяет:
    - Получение истории сделок за период
    - Использование дефолтного периода (30 дней)
    - Структуру данных сделок
    """
    if not mt5_credentials.get("login"):
        pytest.skip("MT5 credentials not configured")

    client = client_mod.MetaTraderClient(
        login=mt5_credentials.get("login"),
        password=mt5_credentials.get("password"),
        server=mt5_credentials.get("server"),
    )

    try:
        assert client.connect() is True

        # Test get_history with default date range (30 days)
        history = client.get_history()
        assert isinstance(history, list), "get_history should return list"
        
        # If there's any history, verify structure
        if len(history) > 0:
            deal = history[0]
            assert "ticket" in deal and deal["ticket"] > 0
            assert "order" in deal
            assert "time" in deal
            assert "type" in deal
            assert "entry" in deal
            assert "symbol" in deal
            assert "volume" in deal
            assert "price" in deal
            assert "commission" in deal
            assert "swap" in deal
            assert "profit" in deal

        # Test get_history with custom date range
        from datetime import datetime, timedelta
        date_to = datetime.now()
        date_from = date_to - timedelta(days=7)
        
        history_week = client.get_history(date_from=date_from, date_to=date_to)
        assert isinstance(history_week, list), "get_history with dates should return list"

    finally:
        client.disconnect()