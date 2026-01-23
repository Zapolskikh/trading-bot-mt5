import pytest
import metatrader_client.client as client_mod


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
    client = client_mod.MetaTraderClient(
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

        # Place limit order
        order_result = client.place_order(
            symbol=symbol,
            side="buy",
            volume=order_amount_usd,
            order_type="limit",
            price=limit_price,
            volume_currency="usd",
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
