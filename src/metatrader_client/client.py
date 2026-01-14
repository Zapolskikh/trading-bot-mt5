from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple, Callable
from datetime import datetime
import pandas as pd
import logging
from decimal import Decimal, ROUND_HALF_UP


def _mt5_module():
    """Dynamic import for MetaTrader5 to avoid static import errors in non-configured environments."""
    try:
        return __import__("MetaTrader5")
    except (ImportError, ModuleNotFoundError):
        return None


class MetaTraderClient:
    """
    Большой класс-обёртка над MetaTrader5 (MT5).
    Ответственность:
    - Подключение
    - Данные (тик/бар)
    - Торговые операции
    - Позиции/ордера/история
    - Данные портфеля
    """

    def __init__(self, login: Optional[int] = None, password: Optional[str] = None, server: Optional[str] = None):
        """Initialize MT5 client.

        Credentials are provided via constructor to avoid passing secrets to connect().
        """
        self.login = login
        self.password = password
        self.server = server
        self.connected = False
        self.mt5: Any = _mt5_module()
        self.logger = logging.getLogger(__name__)

    def connect(self, portable: bool = True) -> bool:
        """Connect to the MT5 terminal using credentials provided in __init__."""
        masked_login = str(self.login) if self.login is not None else "None"
        masked_server = self.server or "None"
        self.logger.info(f"[MT5] connect(login={masked_login}, server={masked_server})")

        try:
            mt5 = self.mt5
            if mt5 is None:
                self.logger.error("[MT5] module not available — connection failed")
                self.connected = False
                return False
            # Initialize terminal with credentials and portable mode
            result = mt5.initialize(
                login=self.login,
                password=self.password,
                server=self.server,
                portable=portable,
            )
            if not result:
                code, msg = self.last_error()
                self.logger.error(f"[MT5] initialize failed: {code} {msg}")
                self.connected = False
                return False

            # If credentials provided, ensure account login explicitly
            if self.login is not None:
                if not mt5.login(login=self.login, password=self.password, server=self.server):
                    code, msg = self.last_error()
                    self.logger.error(f"[MT5] login failed: {code} {msg}")
                    self.connected = False
                    return False

            # Validate terminal/account status
            term_info = mt5.terminal_info()
            account_info = mt5.account_info()
            if term_info is None or account_info is None:
                code, msg = self.last_error()
                self.logger.error(f"[MT5] terminal/account not available: {code} {msg}")
                self.connected = False
                return False

            self.connected = True
            self.logger.info(
                "[MT5] connected:"
                f" login={getattr(account_info, 'login', self.login)} server={getattr(account_info, 'server', self.server)}"
            )
            return True
        except Exception:
            self.logger.exception("[MT5] unexpected error during connect")
            self.connected = False
            return False

    def disconnect(self):
        """Disconnect from the MT5 terminal and reset local state."""
        self.logger.info("[MT5] disconnect() called")
        if self.connected:
            try:
                if self.mt5 is not None:
                    self.mt5.shutdown()
            finally:
                self.connected = False
                self.logger.info("[MT5] disconnected")

    def is_connected(self) -> bool:
        """Check if the MT5 terminal and account are available."""
        try:
            mt5 = self.mt5
            if mt5 is None:
                self.logger.debug("[MT5] is_connected -> False (module missing)")
                return False
            # terminal_info() and account_info() return None if not initialized/connected
            term_info = mt5.terminal_info()
            account_info = mt5.account_info()
            if term_info is None or account_info is None:
                self.logger.debug("[MT5] is_connected -> False (no terminal/account)")
                return False
            self.logger.debug("[MT5] is_connected -> True")
            return True
        except Exception:
            self.logger.exception("[MT5] is_connected -> False (exception)")
            return False

    def get_status(self) -> Dict[str, Any]:
        """Return connection status and basic account/terminal info."""
        self.logger.debug("[MT5] get_status()")
        status: Dict[str, Any] = {"connected": self.is_connected()}
        if not status["connected"]:
            return status

        try:
            mt5 = self.mt5
            if mt5 is None:
                return status
            acc = mt5.account_info()
            ver = mt5.version()
            status.update(
                {
                    "login": acc.login if acc else self.login,
                    "server": acc.server if acc else self.server,
                    "balance": acc.balance if acc else None,
                    "equity": acc.equity if acc else None,
                    "build": ver[2] if isinstance(ver, tuple) and len(ver) >= 3 else None,
                }
            )
        except Exception:
            # Оставляем базовый статус
            pass
        return status

    def last_error(self) -> Tuple[int, str]:
        """Return the last MT5 error code and message (if available)."""
        try:
            mt5 = self.mt5
            if mt5 is None:
                self.logger.debug("[MT5] last_error -> module missing")
                return -1, "unknown"
            code, msg = mt5.last_error()
            self.logger.debug(f"[MT5] last_error -> {code} {msg}")
            return int(code), str(msg)
        except Exception:
            self.logger.exception("[MT5] last_error -> exception")
            return -1, "unknown"

    def _ensure_mt5(
        self,
        context: str,
        error_factory: Callable[[str, int], Dict[str, Any]],
    ) -> Tuple[Any, Optional[Dict[str, Any]]]:
        """Common pre-checks for trading operations.

        Ensures connection and MT5 module availability. Returns a tuple of
        (mt5_module, error_response). If an error occurs, mt5_module is None
        and error_response contains a method-specific error dict from
        ``error_factory``.

        Args:
            context: Method name for logging (e.g., "place_order").
            error_factory: Callable that builds an error dict for this method.

        Returns:
            Tuple of (mt5_module, error_response).
        """
        if not self.is_connected():
            self.logger.error(f"[MT5] {context}: not connected")
            return None, error_factory("Not connected to MT5", -1)

        mt5: Any = self.mt5
        if mt5 is None:
            self.logger.error(f"[MT5] {context}: module missing")
            return None, error_factory("MT5 module not available", -1)

        return mt5, None

    def get_market_data(self, symbol: str, timeframe: str, window: int) -> pd.DataFrame:
        """Fetch OHLCV bars as pandas DataFrame indexed by time."""
        self.logger.debug(f"[MT5] get_market_data(symbol={symbol}, timeframe={timeframe}, window={window})")

        if not self.is_connected():
            self.logger.warning("[MT5] get_market_data: not connected")
            return pd.DataFrame()

        try:
            mt5 = self.mt5
            if mt5 is None:
                self.logger.error("[MT5] get_market_data: module missing")
                return pd.DataFrame()

            # Map timeframe string to MT5 constant
            timeframe_map = {
                "M1": mt5.TIMEFRAME_M1,
                "M5": mt5.TIMEFRAME_M5,
                "M15": mt5.TIMEFRAME_M15,
                "M30": mt5.TIMEFRAME_M30,
                "H1": mt5.TIMEFRAME_H1,
                "H4": mt5.TIMEFRAME_H4,
                "D1": mt5.TIMEFRAME_D1,
                "W1": mt5.TIMEFRAME_W1,
                "MN1": mt5.TIMEFRAME_MN1,
            }

            if timeframe not in timeframe_map:
                self.logger.error(f"[MT5] get_market_data: unsupported timeframe {timeframe}")
                return pd.DataFrame()

            tf = timeframe_map[timeframe]

            # Request bars from MT5
            rates = mt5.copy_rates_from_pos(symbol, tf, 0, window)

            if rates is None or len(rates) == 0:
                code, msg = self.last_error()
                self.logger.error(f"[MT5] get_market_data: copy_rates failed: {code} {msg}")
                return pd.DataFrame()

            # Convert to DataFrame with datetime index
            data = []
            for rate in rates:
                data.append(
                    {
                        "time": datetime.fromtimestamp(rate[0]),
                        "open": rate[1],
                        "high": rate[2],
                        "low": rate[3],
                        "close": rate[4],
                        "tick_volume": rate[5],
                        "real_volume": rate[6],
                        "spread": rate[7],
                    }
                )

            df = pd.DataFrame(data)

            # Set time as index and ensure proper datetime type
            df["time"] = pd.to_datetime(df["time"])
            df.set_index("time", inplace=True)

            # Ensure data types are correct for technical analysis
            for col in ["open", "high", "low", "close"]:
                df[col] = df[col].astype(float)

            for col in ["tick_volume", "real_volume", "spread"]:
                df[col] = df[col].astype(int)

            self.logger.debug(f"[MT5] get_market_data: fetched {len(df)} bars, shape={df.shape}")
            return df

        except Exception as e:
            self.logger.exception(f"[MT5] get_market_data: exception: {e}")
            return pd.DataFrame()

    def get_tick(self, symbol: str) -> Dict[str, Any]:
        """Получение последнего тика в реальном времени для символа.

        Тик содержит текущие цены bid/ask/last и объемы, необходим для:
        - Проверки текущей цены перед открытием позиции
        - Расчета маржи при открытии ордера
        - Оценки ликвидности (spread между bid и ask)
        - Валидации цены в Strategy перед входом

        Args:
            symbol: Trading symbol (e.g., "EURUSD").

        Returns:
            Dict with tick data: {
                "time": datetime,
                "bid": float,      # Current bid price
                "ask": float,      # Current ask price
                "last": float,     # Last traded price
                "volume": int,     # Current tick volume
                "spread": float    # ask - bid spread
            }
            Returns empty dict if connection lost or symbol not available.
        """
        self.logger.debug(f"[MT5] get_tick(symbol={symbol})")

        if not self.is_connected():
            self.logger.warning("[MT5] get_tick: not connected")
            return {}

        try:
            mt5 = self.mt5
            if mt5 is None:
                self.logger.error("[MT5] get_tick: module missing")
                return {}

            # Request last tick for symbol
            tick = mt5.symbol_info_tick(symbol)

            if tick is None:
                code, msg = self.last_error()
                self.logger.error(f"[MT5] get_tick: symbol_info_tick failed: {code} {msg}")
                return {}

            # Convert to dict with readable format
            result = {
                "time": datetime.fromtimestamp(tick.time),
                "bid": tick.bid,
                "ask": tick.ask,
                "last": tick.last,
                "volume": tick.volume,
                "spread": tick.ask - tick.bid,
            }

            self.logger.debug(
                f"[MT5] get_tick: {symbol} bid={tick.bid:.5f} ask={tick.ask:.5f} spread={result['spread']:.5f}"
            )
            return result

        except Exception as e:
            self.logger.exception(f"[MT5] get_tick: exception: {e}")
            return {}

    def place_order(
        self,
        symbol: str,
        side: str,
        volume: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        order_type: str = "market",
        price: Optional[float] = None,
        volume_currency: str = "lots",
    ) -> Dict[str, Any]:
        """Отправка торгового ордера в MT5 терминал.

        ═══════════════════════════════════════════════════════════════════════════
        MT5 ORDER_SEND SPECIFICATION
        ═══════════════════════════════════════════════════════════════════════════

        Метод использует mt5.order_send(MqlTradeRequest) для отправки торговых
        операций. MqlTradeRequest содержит полное описание действия:

        СТРУКТУРА ЗАПРОСА (MqlTradeRequest):
        ────────────────────────────────────
        - action: Тип операции (TRADE_ACTION_DEAL для рыночных/лимитных)
        - magic: ID советника для аналитики
        - symbol: Наименование инструмента (EURUSD, GBPUSD и т.д.)
        - volume: Объем в ЛОТАХ (0.01, 0.1, 1.0, 10.0 и т.д.)
        - type: Тип ордера (ORDER_TYPE_BUY, ORDER_TYPE_SELL и т.д.)
        - price: Цена исполнения (не нужна для рыночных ордеров)
        - sl: Цена Stop Loss (защита от убытков)
        - tp: Цена Take Profit (фиксация прибыли)
        - deviation: Макс отклонение от цены в пунктах (для рыночных)
        - comment: Комментарий к ордеру

        ТИПЫ ОРДЕРОВ (ORDER_TYPE):
        ──────────────────────────
        Рыночные (TRADE_ACTION_DEAL):
        • ORDER_TYPE_BUY    - Рыночная покупка (исполняется по ASK)
        • ORDER_TYPE_SELL   - Рыночная продажа (исполняется по BID)

        Отложенные (TRADE_ACTION_PENDING):
        • ORDER_TYPE_BUY_LIMIT   - Лимит покупка ниже цены
        • ORDER_TYPE_SELL_LIMIT  - Лимит продажа выше цены
        • ORDER_TYPE_BUY_STOP    - Стоп покупка выше цены
        • ORDER_TYPE_SELL_STOP   - Стоп продажа ниже цены

        КОНВЕРТАЦИЯ ОБЪЕМА:
        ──────────────────
        volume_currency может быть:
        • "lots" (default) - объем уже в лотах, используется как есть
        • "usd" - объем в долларах, конвертируется через usd_to_lots()
        • "eur" - объем в евро, конвертируется через eur_to_lots()

        Пример расчета: 10000 USD на EURUSD (contract_size=100000)
        → lots = 10000 / 100000 = 0.1 лот

        РЕЗУЛЬТАТ (MqlTradeResult):
        ──────────────────────────
        - retcode: Код результата (TRADE_RETCODE_DONE = успех)
        - deal: Ticket сделки (если рыночный ордер исполнен)
        - order: Ticket ордера (если отложенный ордер создан)
        - volume: Реально исполненный объем
        - price: Цена исполнения
        - comment: Комментарий сервера об исполнении

        Args:
            symbol: Торговая пара (EURUSD, GBPUSD, XAUUSD и т.д.)
            side: Направление торговли ("buy" или "sell")
            volume: Объем торговли (размер зависит от volume_currency)
            sl: Цена Stop Loss (опционально)
            tp: Цена Take Profit (опционально)
            order_type: Тип ордера ("market", "limit", "stop"). Default: "market"
            price: Цена для лимит/стоп ордеров. Игнорируется для рыночных.
            volume_currency: В какой валюте указан объем:
                            "lots" - в лотах (default)
                            "usd" - в долларах США
                            "eur" - в евро

        Returns:
            Dict с результатом исполнения:
            {
                "success": bool,           # True если ордер принят
                "ticket": int,             # ID сделки/ордера
                "volume": float,           # Реально исполненный объем
                "price": float,            # Цена исполнения
                "comment": str,            # Комментарий сервера
                "retcode": int,            # Код ошибки (0 = успех)
                "action": str              # Выполненное действие
            }
            Returns {"success": False, ...} если ошибка подключения/валидации.
        """
        self.logger.info(
            f"[MT5] place_order(symbol={symbol}, side={side}, volume={volume} {volume_currency}, type={order_type},"
            f" price={price}, sl={sl}, tp={tp})"
        )

        def _order_error(comment: str, retcode: int = -1) -> Dict[str, Any]:
            return {
                "success": False,
                "ticket": 0,
                "volume": 0,
                "price": 0,
                "comment": comment,
                "retcode": retcode,
                "action": "none",
            }

        mt5, err = self._ensure_mt5("place_order", _order_error)
        if err:
            return err

        try:
            # mt5 pre-checked above

            # 1. Валидация и конвертация объема
            actual_volume = volume
            if volume_currency.lower() == "usd":
                actual_volume = self.usd_to_lots(volume, symbol)
                if actual_volume == 0:
                    self.logger.error("[MT5] place_order: USD to lots conversion failed")
                    return {
                        "success": False,
                        "ticket": 0,
                        "volume": 0,
                        "price": 0,
                        "comment": "USD to lots conversion failed",
                        "retcode": -1,
                        "action": "none",
                    }
                self.logger.debug(f"[MT5] place_order: converted {volume} USD → {actual_volume} lots")

            elif volume_currency.lower() == "eur":
                actual_volume = self.eur_to_lots(volume, symbol)
                if actual_volume == 0:
                    self.logger.error("[MT5] place_order: EUR to lots conversion failed")
                    return {
                        "success": False,
                        "ticket": 0,
                        "volume": 0,
                        "price": 0,
                        "comment": "EUR to lots conversion failed",
                        "retcode": -1,
                        "action": "none",
                    }
                self.logger.debug(f"[MT5] place_order: converted {volume} EUR → {actual_volume} lots")

            # 2. Определение конфигурации ордера через mapping
            side_lower = side.lower()
            type_lower = order_type.lower()
            mapping = {
                ("buy", "market"): (mt5.TRADE_ACTION_DEAL, mt5.ORDER_TYPE_BUY, False),
                ("sell", "market"): (mt5.TRADE_ACTION_DEAL, mt5.ORDER_TYPE_SELL, False),
                ("buy", "limit"): (mt5.TRADE_ACTION_PENDING, mt5.ORDER_TYPE_BUY_LIMIT, True),
                ("sell", "limit"): (mt5.TRADE_ACTION_PENDING, mt5.ORDER_TYPE_SELL_LIMIT, True),
                ("buy", "stop"): (mt5.TRADE_ACTION_PENDING, mt5.ORDER_TYPE_BUY_STOP, True),
                ("sell", "stop"): (mt5.TRADE_ACTION_PENDING, mt5.ORDER_TYPE_SELL_STOP, True),
            }

            config = mapping.get((side_lower, type_lower))
            if config is None:
                self.logger.error(f"[MT5] place_order: invalid side/type: {side}/{order_type}")
                return _order_error(f"Invalid side/type: {side}/{order_type}")

            order_action, order_type_const, requires_price = config
            if requires_price and price is None:
                self.logger.error("[MT5] place_order: price is required for limit/stop")
                return _order_error("Price is required for limit/stop orders")

            # 3. Построение MqlTradeRequest структуры
            # Разные параметры для маркет и отложенных ордеров
            is_pending_order = order_type.lower() in ("limit", "stop")

            request = {
                "action": order_action,
                "symbol": symbol,
                "volume": float(actual_volume),
                "type": order_type_const,
                "price": float(price) if price is not None else 0.0,
                "sl": float(sl) if sl is not None else 0.0,
                "tp": float(tp) if tp is not None else 0.0,
                "magic": 42,  # ID советника для аналитики
                "comment": f"[TradingBot] {side_lower} {order_type}",
                "type_time": mt5.ORDER_TIME_GTC,  # Good Till Cancel (до отмены)
            }

            # Для маркет-ордеров добавляем deviation и ORDER_FILLING_FOK
            if not is_pending_order:
                request["deviation"] = 10  # макс отклонение в пунктах для рыночных
                request["type_filling"] = mt5.ORDER_FILLING_FOK  # Fill or Kill для маркет
            else:
                # Для отложенных ордеров используем ORDER_FILLING_IOC
                request["type_filling"] = mt5.ORDER_FILLING_IOC  # Immediate or Cancel для отложенных

            self.logger.debug(f"[MT5] place_order: sending request: {request}")

            # 4. Отправка ордера в MT5
            result = mt5.order_send(request)

            if result is None:
                code, msg = self.last_error()
                self.logger.error(f"[MT5] place_order: order_send returned None: {code} {msg}")
                return _order_error(f"order_send failed: {msg}", code)

            # 5. Обработка результата
            retcode = result.retcode
            success = retcode == mt5.TRADE_RETCODE_DONE

            response = {
                "success": success,
                "ticket": result.order if result.order else result.deal if result.deal else 0,
                "volume": result.volume if hasattr(result, "volume") else actual_volume,
                "price": result.price if hasattr(result, "price") else price or 0.0,
                "comment": result.comment if hasattr(result, "comment") else "",
                "retcode": retcode,
                "action": f"{side_lower} {order_type}",
            }

            if success:
                self.logger.info(
                    f"[MT5] place_order: SUCCESS! Ticket={response['ticket']}, Volume={response['volume']},"
                    f" Price={response['price']}"
                )
            else:
                self.logger.warning(f"[MT5] place_order: FAILED! Retcode={retcode}, Comment={response['comment']}")

            return response

        except Exception as e:
            self.logger.exception(f"[MT5] place_order: exception: {e}")
            return _order_error(f"Exception: {str(e)}")

    def modify_order(
        self,
        order_id: int,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Модификация параметров существующего ордера (SL/TP/цена).

        ═══════════════════════════════════════════════════════════════════════════
        MT5 ORDER_MODIFY SPECIFICATION
        ═══════════════════════════════════════════════════════════════════════════

        Метод используется для изменения параметров АКТИВНОГО отложенного ордера
        (не сделки, которая уже исполнена). Может быть изменено:
        - price: Новая цена триггера (для BUY_LIMIT, SELL_LIMIT, BUY_STOP, SELL_STOP)
        - sl: Stop Loss цена
        - tp: Take Profit цена

        ОГРАНИЧЕНИЯ:
        ────────────
        • Для рыночных позиций (DEAL) используй close_position() или изменяй через
          OrderModify() только параметры SL/TP открытой позиции
        • Для отложенных ордеров (PENDING) можно менять цену и SL/TP
        • SL всегда ниже текущей цены для BUY, выше для SELL
        • TP всегда выше текущей цены для BUY, ниже для SELL
        • Нельзя закрывать ордер через modify - используй order_send() с TRADE_ACTION_REMOVE

        СТРУКТУРА ЗАПРОСА (MqlTradeRequest):
        ────────────────────────────────────
        - action: TRADE_ACTION_MODIFY (только для отложенных ордеров)
        - order: Ticket существующего ордера (который менять)
        - symbol: Наименование инструмента (должно совпадать с символом ордера)
        - volume: Новый объем (опционально, если меняем)
        - price: Новая цена триггера (для limit/stop ордеров)
        - sl: Новая цена Stop Loss
        - tp: Новая цена Take Profit
        - comment: Новый комментарий (опционально)
        - type_filling: ORDER_FILLING_RETURN (стандартное)
        - type_time: ORDER_TIME_GTC (Good Till Cancel)

        РЕЗУЛЬТАТ (MqlTradeResult):
        ──────────────────────────
        - retcode: Код результата (TRADE_RETCODE_DONE = успех)
        - order: Ticket модифицированного ордера
        - comment: Комментарий сервера

        КОДЫ ОШИБОК:
        ────────────
        • TRADE_RETCODE_DONE (10009) - успешно
        • TRADE_RETCODE_INVALID_TRADE (10006) - ордер не найден или не активен
        • TRADE_RETCODE_PRICE_OFF (10015) - неправильная цена (вне допустимого диапазона)
        • TRADE_RETCODE_INVALID_STOPS (10017) - неправильные SL/TP

        Args:
            order_id: Ticket активного ордера для модификации (целое число)
            sl: Новая цена Stop Loss (опционально)
            tp: Новая цена Take Profit (опционально)
            price: Новая цена триггера для limit/stop ордеров (опционально)

        Returns:
            Dict с результатом:
            {
                "success": bool,           # True если модификация успешна
                "ticket": int,             # Ticket модифицированного ордера
                "retcode": int,            # Код результата
                "comment": str,            # Комментарий сервера
                "old_values": Dict,        # Старые значения (price, sl, tp)
                "new_values": Dict         # Новые значения (price, sl, tp)
            }
            Returns {"success": False, ...} если ошибка подключения/валидации.
        """
        self.logger.info(f"[MT5] modify_order(order_id={order_id}, sl={sl}, tp={tp}, price={price})")

        def _modify_error(comment: str, retcode: int = -1) -> Dict[str, Any]:
            return {
                "success": False,
                "ticket": 0,
                "retcode": retcode,
                "comment": comment,
                "old_values": {},
                "new_values": {},
            }

        mt5, err = self._ensure_mt5("modify_order", _modify_error)
        if err:
            return err

        try:
            # mt5 pre-checked above

            # 1. Получить информацию о существующем ордере
            orders = mt5.orders_get(ticket=order_id)
            if orders is None or len(orders) == 0:
                code, msg = self.last_error()
                self.logger.error(f"[MT5] modify_order: order {order_id} not found: {code} {msg}")
                return _modify_error(f"Order not found: {msg}", code)

            order = orders[0]

            # Сохранить старые значения
            old_values = {
                "price": order.price_open if hasattr(order, "price_open") else 0.0,
                "sl": order.sl if hasattr(order, "sl") else 0.0,
                "tp": order.tp if hasattr(order, "tp") else 0.0,
            }

            self.logger.debug(f"[MT5] modify_order: found order {order_id}: symbol={order.symbol}, state={order.state}")
            self.logger.debug(
                f"[MT5] modify_order: old values - price={old_values['price']:.5f}, sl={old_values['sl']:.5f},"
                f" tp={old_values['tp']:.5f}"
            )

            # 2. Построить MqlTradeRequest
            request = {
                "action": mt5.TRADE_ACTION_MODIFY,
                "order": order_id,
                "symbol": order.symbol,
                "price": price if price is not None else old_values["price"],
                "sl": sl if sl is not None else old_values["sl"],
                "tp": tp if tp is not None else old_values["tp"],
                "magic": 42,
                "comment": "[TradingBot] modified",
                "type_filling": mt5.ORDER_FILLING_RETURN,
                "type_time": mt5.ORDER_TIME_GTC,
            }

            self.logger.debug(f"[MT5] modify_order: sending request: {request}")

            # 3. Отправить запрос на модификацию
            result = mt5.order_send(request)

            if result is None:
                code, msg = self.last_error()
                self.logger.error(f"[MT5] modify_order: order_send returned None: {code} {msg}")
                resp = _modify_error(f"order_send failed: {msg}", code)
                resp["old_values"] = old_values
                return resp

            # 4. Обработать результат
            retcode = result.retcode
            success = retcode == mt5.TRADE_RETCODE_DONE

            new_values = {
                "price": price if price is not None else old_values["price"],
                "sl": sl if sl is not None else old_values["sl"],
                "tp": tp if tp is not None else old_values["tp"],
            }

            response = {
                "success": success,
                "ticket": result.order if hasattr(result, "order") else order_id,
                "retcode": retcode,
                "comment": result.comment if hasattr(result, "comment") else "",
                "old_values": old_values,
                "new_values": new_values,
            }

            if success:
                self.logger.info(f"[MT5] modify_order: SUCCESS! Order {order_id} modified")
                self.logger.debug(
                    f"[MT5]   Price: {old_values['price']:.5f} → {new_values['price']:.5f}\n[MT5]   SL:   "
                    f" {old_values['sl']:.5f} → {new_values['sl']:.5f}\n[MT5]   TP:    {old_values['tp']:.5f} →"
                    f" {new_values['tp']:.5f}"
                )
            else:
                self.logger.warning(f"[MT5] modify_order: FAILED! Retcode={retcode}, Comment={response['comment']}")

            return response

        except Exception as e:
            self.logger.exception(f"[MT5] modify_order: exception: {e}")
            return _modify_error(f"Exception: {str(e)}")

    def cancel_order(self, order_id: int) -> Dict[str, Any]:
        """Отмена (удаление) активного отложенного ордера.

        ═══════════════════════════════════════════════════════════════════════════
        MT5 ORDER_CANCEL SPECIFICATION
        ═══════════════════════════════════════════════════════════════════════════

        Метод удаляет активный отложенный ордер из очереди. Ордер должен быть
        в состоянии ORDER_STATE_PLACED (активный). После отмены ордер переходит
        в состояние ORDER_STATE_CANCELED.

        ВАЖНО:
        ──────
        • Нельзя отменить уже ИСПОЛНЕННЫЙ ордер (сделку) - используй close_position()
        • Нельзя отменить позицию (открытую сделку) - используй close_position()
        • Можно отменить только ЗАЯВКУ (отложенный ордер) - BUY_LIMIT, SELL_LIMIT и т.д.

        СТРУКТУРА ЗАПРОСА (MqlTradeRequest):
        ────────────────────────────────────
        - action: TRADE_ACTION_REMOVE (удаление ордера)
        - order: Ticket ордера для отмены
        - symbol: Наименование инструмента (должно совпадать с символом ордера)
        - comment: Опциональный комментарий причины отмены

        РЕЗУЛЬТАТ (MqlTradeResult):
        ──────────────────────────
        - retcode: Код результата (TRADE_RETCODE_DONE = успех)
        - order: Ticket удаленного ордера
        - comment: Комментарий сервера

        КОДЫ ОШИБОК:
        ────────────
        • TRADE_RETCODE_DONE (10009) - ордер успешно отменен
        • TRADE_RETCODE_INVALID_TRADE (10006) - ордер не найден или уже исполнен
        • TRADE_RETCODE_TRADE_DISABLED (10019) - торговля отключена на счете

        Args:
            order_id: Ticket отложенного ордера для отмены (целое число)

        Returns:
            Dict с результатом:
            {
                "success": bool,           # True если отмена успешна
                "ticket": int,             # Ticket отмененного ордера
                "retcode": int,            # Код результата
                "comment": str             # Комментарий сервера
            }
            Returns {"success": False, ...} если ошибка подключения/валидации.
        """
        self.logger.info(f"[MT5] cancel_order(order_id={order_id})")

        def _cancel_error(comment: str, retcode: int = -1) -> Dict[str, Any]:
            return {"success": False, "ticket": 0, "retcode": retcode, "comment": comment}

        mt5, err = self._ensure_mt5("cancel_order", _cancel_error)
        if err:
            return err

        try:
            # mt5 pre-checked above

            # 1. Получить информацию о ордере
            orders = mt5.orders_get(ticket=order_id)
            if orders is None or len(orders) == 0:
                code, msg = self.last_error()
                self.logger.error(f"[MT5] cancel_order: order {order_id} not found: {code} {msg}")
                return _cancel_error(f"Order not found: {msg}", code)

            order = orders[0]

            self.logger.debug(
                f"[MT5] cancel_order: found order {order_id}: symbol={order.symbol}, state={order.state},"
                f" price={order.price_open:.5f}"
            )

            # 2. Построить MqlTradeRequest
            request = {
                "action": mt5.TRADE_ACTION_REMOVE,  # Удаление ордера
                "order": order_id,
                "symbol": order.symbol,
                "comment": "[TradingBot] canceled",
            }

            self.logger.debug(f"[MT5] cancel_order: sending request: {request}")

            # 3. Отправить запрос на отмену
            result = mt5.order_send(request)

            if result is None:
                code, msg = self.last_error()
                self.logger.error(f"[MT5] cancel_order: order_send returned None: {code} {msg}")
                return _cancel_error(f"order_send failed: {msg}", code)

            # 4. Обработать результат
            retcode = result.retcode
            success = retcode == mt5.TRADE_RETCODE_DONE

            response = {
                "success": success,
                "ticket": result.order if hasattr(result, "order") else order_id,
                "retcode": retcode,
                "comment": result.comment if hasattr(result, "comment") else "",
            }

            if success:
                self.logger.info(f"[MT5] cancel_order: SUCCESS! Order {order_id} canceled")
            else:
                self.logger.warning(f"[MT5] cancel_order: FAILED! Retcode={retcode}, Comment={response['comment']}")

            return response

        except Exception as e:
            self.logger.exception(f"[MT5] cancel_order: exception: {e}")
            return _cancel_error(f"Exception: {str(e)}")

    def close_position(self, position_id: str, lots: Optional[float] = None) -> str:
        """Закрытие позиции полностью или частично. Возвращает deal_id.

        TODO: Реализовать метод закрытия открытой позиции через TRADE_ACTION_DEAL.
        Требуется: получение информации о позиции, расчет объема, выставление market order.
        """
        self.logger.info(f"[MT5] close_position(position_id={position_id}, lots={lots})")
        return "deal_0001"

    def get_positions(self) -> List[Dict[str, Any]]:
        """Получение списка открытых позиций.

        TODO: Реализовать метод получения активных позиций через mt5.positions_get().
        Требуется: парсинг структуры TradePosition, преобразование в словари.
        """
        self.logger.debug("[MT5] get_positions()")
        return []

    def get_orders(self) -> List[Dict[str, Any]]:
        """Получение списка всех активных (отложенных) ордеров.

        ═══════════════════════════════════════════════════════════════════════════
        MT5 ORDERS_GET SPECIFICATION
        ═══════════════════════════════════════════════════════════════════════════

        Возвращает список АКТИВНЫХ ОТЛОЖЕННЫХ ордеров (заявок) на счете.
        Это НЕ включает уже ИСПОЛНЕННЫЕ сделки (использовать get_history() для них).

        ОТЛОЖЕННЫЕ ОРДЕРА (PENDING ORDERS):
        ──────────────────────────────────
        • ORDER_TYPE_BUY_LIMIT   - Лимит покупка ниже текущей цены
        • ORDER_TYPE_SELL_LIMIT  - Лимит продажа выше текущей цены
        • ORDER_TYPE_BUY_STOP    - Стоп покупка выше текущей цены
        • ORDER_TYPE_SELL_STOP   - Стоп продажа ниже текущей цены

        ИНФОРМАЦИЯ В ОРДЕРЕ:
        ───────────────────
        • ticket: Уникальный номер ордера
        • symbol: Наименование инструмента
        • type: Тип ордера (BUY_LIMIT, SELL_LIMIT, BUY_STOP, SELL_STOP)
        • state: Состояние (ORDER_STATE_PLACED - активный)
        • volume: Объем в лотах
        • price_open: Цена триггера (когда сработает)
        • sl: Цена Stop Loss
        • tp: Цена Take Profit
        • time_setup: Время создания ордера
        • time_setup_msc: Время создания (миллисекунды)
        • time_expiration: Время истечения (если установлено)
        • comment: Комментарий
        • magic: ID советника
        • reason: Причина создания

        ОТЛИЧИЯ ОТ ПОЗИЦИЙ:
        ──────────────────
        • get_orders() → АКТИВНЫЕ ОТЛОЖЕННЫЕ ОРДЕРА (заявки в очереди)
        • get_positions() → ОТКРЫТЫЕ ПОЗИЦИИ (уже исполненные сделки)
        • get_history() → ИСТОРИЧЕСКИЕ СДЕЛКИ (закрытые позиции + исполненные ордера)

        Returns:
            List[Dict] со списком активных ордеров. Каждый ордер содержит:
            [
                {
                    "ticket": int,              # Уникальный ID ордера
                    "symbol": str,              # Символ (EURUSD, GBPUSD и т.д.)
                    "type": str,                # Тип (buy_limit, sell_limit, buy_stop, sell_stop)
                    "state": str,               # Состояние (placed, request_add, request_modify, etc.)
                    "volume": float,            # Объем в лотах
                    "price": float,             # Цена триггера
                    "sl": float,                # Stop Loss цена
                    "tp": float,                # Take Profit цена
                    "time_setup": datetime,     # Время создания
                    "comment": str,             # Комментарий
                    "magic": int                # ID советника
                },
                ...
            ]
            Returns [] (пустой список) если нет активных ордеров или ошибка подключения.
        """
        self.logger.debug("[MT5] get_orders()")

        if not self.is_connected():
            self.logger.warning("[MT5] get_orders: not connected")
            return []

        try:
            mt5 = self.mt5
            if mt5 is None:
                self.logger.error("[MT5] get_orders: module missing")
                return []

            # Получить все активные ордера
            orders = mt5.orders_get()

            if orders is None or len(orders) == 0:
                self.logger.debug("[MT5] get_orders: no active orders found")
                return []

            # Конвертировать в список дictionarios
            result = []
            type_names = {
                mt5.ORDER_TYPE_BUY_LIMIT: "buy_limit",
                mt5.ORDER_TYPE_SELL_LIMIT: "sell_limit",
                mt5.ORDER_TYPE_BUY_STOP: "buy_stop",
                mt5.ORDER_TYPE_SELL_STOP: "sell_stop",
            }

            for order in orders:
                # Попробуем получить объем из разных возможных полей
                volume = getattr(order, "volume_initial", getattr(order, "volume", 0.0))

                order_dict = {
                    "ticket": order.ticket,
                    "symbol": order.symbol,
                    "type": type_names.get(order.type, f"unknown_{order.type}"),
                    "state": str(order.state),
                    "volume": volume,
                    "price": order.price_open,
                    "sl": order.sl,
                    "tp": order.tp,
                    "time_setup": datetime.fromtimestamp(order.time_setup),
                    "comment": order.comment if hasattr(order, "comment") else "",
                    "magic": order.magic if hasattr(order, "magic") else 0,
                }
                result.append(order_dict)

            self.logger.debug(f"[MT5] get_orders: found {len(result)} active orders")
            for order in result:
                self.logger.debug(
                    f"[MT5]   Ticket {order['ticket']}: {order['symbol']} {order['type']} @"
                    f" {order['price']:.5f} vol={order['volume']}"
                )

            return result

        except Exception as e:
            self.logger.exception(f"[MT5] get_orders: exception: {e}")
            return []

    def get_history(self, since: Optional[str] = None, until: Optional[str] = None) -> List[Dict[str, Any]]:
        """Получение истории сделок/ордеров за указанный период.

        TODO: Реализовать метод получения истории сделок через mt5.history_deals_get().
        Требуется: парсинг дат (since/until), фильтрация по периоду, преобразование в словари.
        """
        self.logger.debug(f"[MT5] get_history(since={since}, until={until})")
        return []

    def get_portfolio(self) -> Dict[str, Any]:
        """Получение метрик портфеля: баланс/эквити/маржа.

        TODO: Реализовать метод получения портфельных метрик через mt5.account_info().
        Требуется: расчет свободной маржи, уровня маржи, других показателей риска.
        """
        self.logger.debug("[MT5] get_portfolio()")
        return {"balance": 0.0, "equity": 0.0, "margin": 0.0, "free_margin": 0.0}

    def get_symbol_info(self, symbol: str) -> Dict[str, Any]:
        """Получение параметров символа для торговли.

        Необходим для:
        - Определения размера одного лота (contract_size)
        - Расчета минимально допустимого объема (min_lot)
        - Определения точности цены (digits, point)
        - Расчета стоимости пункта (tick_value, tick_size)
        - Валидации объема перед отправкой ордера

        Args:
            symbol: Trading symbol (e.g., "EURUSD").

        Returns:
            Dict with symbol parameters: {
                "symbol": str,              # Symbol name
                "digits": int,              # Decimal places in price (5 for EURUSD)
                "point": float,             # One point value (0.00001 for EURUSD)
                "contract_size": float,     # Lot size in units (100000 for EURUSD)
                "lot_step": float,          # Minimum lot step (0.01 for most pairs)
                "min_lot": float,           # Minimum lot to open (0.01 for most pairs)
                "max_lot": float,           # Maximum lot allowed
                "tick_value": float,        # Profit/loss for 1 pip
                "tick_size": float,         # Minimum price movement
                "spread": float,            # Current bid-ask spread in points
                "ask": float,               # Current ask price
                "bid": float                # Current bid price
            }
            Returns empty dict if symbol not available.
        """
        self.logger.debug(f"[MT5] get_symbol_info(symbol={symbol})")

        if not self.is_connected():
            self.logger.warning("[MT5] get_symbol_info: not connected")
            return {}

        try:
            mt5 = self.mt5
            if mt5 is None:
                self.logger.error("[MT5] get_symbol_info: module missing")
                return {}

            # Get symbol info from MT5
            si = mt5.symbol_info(symbol)
            if si is None:
                code, msg = self.last_error()
                self.logger.error(f"[MT5] get_symbol_info: symbol_info failed: {code} {msg}")
                return {}

            # Get current tick for bid/ask
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                self.logger.debug(f"[MT5] get_symbol_info: could not get tick for {symbol}")
                bid, ask = None, None
            else:
                bid = tick.bid
                ask = tick.ask

            result = {
                "symbol": si.name,
                "digits": si.digits,
                "point": si.point,
                "contract_size": si.trade_contract_size,
                "lot_step": si.volume_step,
                "min_lot": si.volume_min,
                "max_lot": si.volume_max,
                "tick_value": si.trade_tick_value,
                "tick_size": si.trade_tick_size,
                "spread": (ask - bid) / si.point if (bid and ask) else None,
                "ask": ask,
                "bid": bid,
            }

            self.logger.debug(
                f"[MT5] get_symbol_info: {symbol} contract_size={si.trade_contract_size} min_lot={si.volume_min}"
            )
            return result

        except Exception as e:
            self.logger.exception(f"[MT5] get_symbol_info: exception: {e}")
            return {}

    def eur_to_lots(self, amount_eur: float, symbol: str) -> float:
        """Конвертирует сумму в евро в объем в лотах для заданного символа.

        Алгоритм:
        1. Получить текущий курс EUR/USD через get_tick("EURUSD")
        2. Конвертировать EUR → USD: amount_usd = amount_eur * eur_usd_rate
        3. Получить contract_size символа через get_symbol_info()
        4. Рассчитать лоты: lots = amount_usd / contract_size

        Args:
            amount_eur: Сумма в евро (например, 1000 евро).
            symbol: Trading symbol (e.g., "EURUSD", "EURGBP").

        Returns:
            Volume in lots (float), rounded to lot_step.
            Returns 0 if conversion fails.
        """
        self.logger.debug(f"[MT5] eur_to_lots(amount_eur={amount_eur}, symbol={symbol})")

        try:
            # Get current EUR/USD rate
            eurusd_tick = self.get_tick("EURUSD")
            if not eurusd_tick:
                self.logger.error("[MT5] eur_to_lots: could not get EURUSD rate")
                return 0.0

            eur_usd_rate = eurusd_tick["bid"]  # Use bid for selling EUR
            amount_usd = amount_eur * eur_usd_rate
            self.logger.debug(f"[MT5] eur_to_lots: {amount_eur} EUR × {eur_usd_rate:.5f} = {amount_usd:.2f} USD")

            # Get symbol info
            sym_info = self.get_symbol_info(symbol)
            if not sym_info:
                self.logger.error(f"[MT5] eur_to_lots: could not get info for {symbol}")
                return 0.0

            contract_size = sym_info["contract_size"]
            lot_step = sym_info["lot_step"]
            min_lot = sym_info["min_lot"]

            # Calculate lots
            lots = amount_usd / contract_size

            # Round to lot_step with Decimal to avoid FP errors
            lots = self._round_to_step(lots, lot_step)

            if lots < min_lot:
                self.logger.warning(f"[MT5] eur_to_lots: calculated {lots} is below min_lot {min_lot}")
                return 0.0

            self.logger.debug(f"[MT5] eur_to_lots: result = {lots} lots")
            return lots

        except Exception as e:
            self.logger.exception(f"[MT5] eur_to_lots: exception: {e}")
            return 0.0

    def usd_to_lots(self, amount_usd: float, symbol: str) -> float:
        """Конвертирует сумму в долларах США в объем в лотах для заданного символа.

        Алгоритм:
        1. Получить contract_size символа через get_symbol_info()
        2. Рассчитать лоты: lots = amount_usd / contract_size
        3. Округлить до lot_step и проверить min_lot

        Args:
            amount_usd: Сумма в долларах (например, 10000 USD).
            symbol: Trading symbol (e.g., "EURUSD").

        Returns:
            Volume in lots (float), rounded to lot_step.
            Returns 0 if conversion fails.
        """
        self.logger.debug(f"[MT5] usd_to_lots(amount_usd={amount_usd}, symbol={symbol})")

        try:
            # Get symbol info
            sym_info = self.get_symbol_info(symbol)
            if not sym_info:
                self.logger.error(f"[MT5] usd_to_lots: could not get info for {symbol}")
                return 0.0

            contract_size = sym_info["contract_size"]
            lot_step = sym_info["lot_step"]
            min_lot = sym_info["min_lot"]

            # Calculate lots
            lots = amount_usd / contract_size
            self.logger.debug(
                f"[MT5] usd_to_lots: {amount_usd} USD / {contract_size} = {lots:.4f} lots (before rounding)"
            )

            # Round to lot_step with Decimal to avoid FP errors
            lots = self._round_to_step(lots, lot_step)

            if lots < min_lot:
                self.logger.warning(f"[MT5] usd_to_lots: calculated {lots} is below min_lot {min_lot}")
                return 0.0

            self.logger.debug(f"[MT5] usd_to_lots: result = {lots} lots")
            return lots

        except Exception as e:
            self.logger.exception(f"[MT5] usd_to_lots: exception: {e}")
            return 0.0

    def _round_to_step(self, value: float, step: float) -> float:
        """Round value to closest multiple of step using Decimal."""
        v = Decimal(str(value))
        s = Decimal(str(step))
        if s == 0:
            return float(v)
        q = (v / s).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return float(q * s)
