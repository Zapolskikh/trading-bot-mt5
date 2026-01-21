from __future__ import annotations
from typing import Any
from datetime import datetime
import pandas as pd
import logging
from decimal import Decimal, ROUND_HALF_UP
import MetaTrader5 as mt5


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

    TIMEFRAMES = {
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
    
    # Max price slippage for market orders in points (10 points = 1 pip for 5-digit quotes)
    # TODO: Move to config file (config.yaml or risk_manager settings)
    DEVIATION = 10
    
    # EA identifier for MT5 (filters bot orders from manual/other bots)
    # TODO: Move to config file (config.yaml)
    MAGIC_NUMBER = 234567


    def __init__(self, login: int, password: str, server: str):
        """Initialize MT5 client."""
        self.login = login
        self.password = password
        self.server = server


    def connect(self, portable: bool = True) -> bool:
        """Connect to the MT5 terminal."""
        try:
            if not mt5.initialize(self.login, self.password, self.server, portable=portable):
                logging.error(f"[MT5] initialize failed: {mt5.last_error()}")
                return False

            if not mt5.login(self.login, self.password, self.server):
                logging.error(f"[MT5] login failed: {mt5.last_error()}")
                return False

            logging.info(f"[MT5] connected: login={self.login} server={self.server}")
            return True
        except Exception:
            logging.exception("[MT5] connect failed")
            return False


    def disconnect(self):
        """Disconnect from the MT5 terminal."""
        mt5.shutdown()


    def get_market_data(self, symbol: str, timeframe: str, window: int) -> pd.DataFrame:
        """Fetch OHLCV bars as pandas DataFrame indexed by time."""
        if timeframe not in self.TIMEFRAMES:
            logging.error(f"[MT5] get_market_data: unsupported timeframe {timeframe}")
            return pd.DataFrame()

        # bars as the numpy array with the named time, open, high, low, close, tick_volume, spread and real_volume columns. 
        # None in case of an error.
        rates = mt5.copy_rates_from_pos(symbol, self.TIMEFRAMES[timeframe], 0, window)

        if rates is None or len(rates) == 0:
            logging.error(f"[MT5] get_market_data failed: {mt5.last_error()}")
            return pd.DataFrame()

        # Convert numpy array to DataFrame directly
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.set_index("time", inplace=True)

        return df


    def get_tick(self, symbol: str) -> dict[str, Any]:
        """Get last tick for symbol with bid/ask/last prices and volume.
        
        Returns empty dict if symbol not available.
        """
        tick = mt5.symbol_info_tick(symbol)
        
        if tick is None:
            logging.error(f"[MT5] get_tick failed: {mt5.last_error()}")
            return {}
        
        return {
            "time": datetime.fromtimestamp(tick.time),
            "bid": tick.bid,
            "ask": tick.ask,
            "last": tick.last,
            "volume": tick.volume,
            "spread": tick.ask - tick.bid,
        }


    def place_order(
        self,
        symbol: str,
        side: str,
        volume: float,
        sl: float | None = None,
        tp: float | None = None,
        order_type: str = "market",
        price: float | None = None,
        volume_currency: str = "lots",
    ) -> dict[str, Any]:
        """Send trading order to MT5.
        
        Args:
            symbol: Trading pair (EURUSD, GBPUSD, etc.)
            side: "buy" or "sell"
            volume: Volume (depends on volume_currency)
            sl: Stop Loss price
            tp: Take Profit price
            order_type: "market", "limit", or "stop"
            price: Price for limit/stop orders
            volume_currency: "lots" (default), "usd", or "eur"
            
        Returns:
            {"success": bool, "ticket": int, "volume": float, "price": float, 
             "comment": str, "retcode": int, "action": str}
        """
        # Convert volume if needed
        actual_volume = volume
        if volume_currency.lower() == "usd":
            actual_volume = self.usd_to_lots(volume, symbol)
            if actual_volume == 0:
                logging.error(f"[MT5] place_order: USD→lots conversion failed")
                return {"success": False, "ticket": 0, "volume": 0, "price": 0,
                        "comment": "USD to lots conversion failed", "retcode": -1, "action": "none"}
        elif volume_currency.lower() == "eur":
            actual_volume = self.eur_to_lots(volume, symbol)
            if actual_volume == 0:
                logging.error(f"[MT5] place_order: EUR→lots conversion failed")
                return {"success": False, "ticket": 0, "volume": 0, "price": 0,
                        "comment": "EUR to lots conversion failed", "retcode": -1, "action": "none"}

        # Determine order configuration
        side_lower = side.lower()
        type_lower = order_type.lower()
        
        # Map (side, type) -> (action, order_type, requires_price)
        order_config = {
            ("buy", "market"): (mt5.TRADE_ACTION_DEAL, mt5.ORDER_TYPE_BUY, False),
            ("sell", "market"): (mt5.TRADE_ACTION_DEAL, mt5.ORDER_TYPE_SELL, False),
            ("buy", "limit"): (mt5.TRADE_ACTION_PENDING, mt5.ORDER_TYPE_BUY_LIMIT, True),
            ("sell", "limit"): (mt5.TRADE_ACTION_PENDING, mt5.ORDER_TYPE_SELL_LIMIT, True),
            ("buy", "stop"): (mt5.TRADE_ACTION_PENDING, mt5.ORDER_TYPE_BUY_STOP, True),
            ("sell", "stop"): (mt5.TRADE_ACTION_PENDING, mt5.ORDER_TYPE_SELL_STOP, True),
        }.get((side_lower, type_lower))
        
        if not order_config:  # Invalid side/type combination from user input
            logging.error(f"[MT5] place_order: invalid side/type: {side}/{order_type}")
            return {"success": False, "ticket": 0, "volume": 0, "price": 0,
                    "comment": f"Invalid side/type: {side}/{order_type}", "retcode": -1, "action": "none"}
        
        order_action, order_type_const, requires_price = order_config
        if requires_price and price is None:  # limit/stop require price
            logging.error("[MT5] place_order: price required for limit/stop")
            return {"success": False, "ticket": 0, "volume": 0, "price": 0,
                    "comment": "Price is required for limit/stop orders", "retcode": -1, "action": "none"}

        # Build request
        request = {
            "action": order_action,
            "symbol": symbol,
            "volume": float(actual_volume),
            "type": order_type_const,
            "price": float(price) if price else 0.0,
            "sl": float(sl) if sl else 0.0,
            "tp": float(tp) if tp else 0.0,
            "magic": self.MAGIC_NUMBER,
            "comment": f"[TradingBot] {side_lower} {type_lower}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK if type_lower == "market" else mt5.ORDER_FILLING_IOC,
        }
        
        if type_lower == "market":
            request["deviation"] = self.DEVIATION

        # Send order
        result = mt5.order_send(request)
        if result is None:
            logging.error(f"[MT5] place_order: order_send failed: {mt5.last_error()}")
            return {"success": False, "ticket": 0, "volume": 0, "price": 0,
                    "comment": "order_send failed", "retcode": -1, "action": "none"}

        # Process result
        success = result.retcode == mt5.TRADE_RETCODE_DONE
        response = {
            "success": success,
            "ticket": result.order or result.deal or 0,
            "volume": getattr(result, "volume", actual_volume),
            "price": getattr(result, "price", price or 0.0),
            "comment": getattr(result, "comment", ""),
            "retcode": result.retcode,
            "action": f"{side_lower} {type_lower}",
        }

        if success:
            logging.info(f"[MT5] place_order SUCCESS: ticket={response['ticket']}, vol={response['volume']}, price={response['price']}")
        else:
            logging.warning(f"[MT5] place_order FAILED: retcode={result.retcode}, comment={response['comment']}")

        return response


    def modify_order(
        self,
        order_id: int,
        sl: float | None = None,
        tp: float | None = None,
        price: float | None = None,
    ) -> dict[str, Any]:
        """Modify existing pending order (SL/TP/price).
        
        Args:
            order_id: Order ticket to modify
            sl: New Stop Loss price
            tp: New Take Profit price
            price: New trigger price for limit/stop orders
            
        Returns:
            {"success": bool, "ticket": int, "retcode": int, "comment": str,
             "old_values": dict, "new_values": dict}
        """
        # Get existing order
        orders = mt5.orders_get(ticket=order_id)
        if orders is None or len(orders) == 0:
            logging.error(f"[MT5] modify_order: order {order_id} not found: {mt5.last_error()}")
            return {"success": False, "ticket": 0, "retcode": -1, "comment": "Order not found",
                    "old_values": {}, "new_values": {}}

        order = orders[0]
        
        # Save old values
        old_values = {
            "price": getattr(order, "price_open", 0.0),
            "sl": getattr(order, "sl", 0.0),
            "tp": getattr(order, "tp", 0.0),
        }

        # Build request
        request = {
            "action": mt5.TRADE_ACTION_MODIFY,
            "order": order_id,
            "symbol": order.symbol,
            "price": price if price is not None else old_values["price"],
            "sl": sl if sl is not None else old_values["sl"],
            "tp": tp if tp is not None else old_values["tp"],
            "magic": self.MAGIC_NUMBER,
            "comment": "[TradingBot] modified",
            "type_filling": mt5.ORDER_FILLING_RETURN,
            "type_time": mt5.ORDER_TIME_GTC,
        }

        # Send modification
        result = mt5.order_send(request)
        if result is None:
            logging.error(f"[MT5] modify_order: order_send failed: {mt5.last_error()}")
            return {"success": False, "ticket": 0, "retcode": -1, "comment": "order_send failed",
                    "old_values": old_values, "new_values": {}}

        # Process result
        success = result.retcode == mt5.TRADE_RETCODE_DONE
        new_values = {
            "price": price if price is not None else old_values["price"],
            "sl": sl if sl is not None else old_values["sl"],
            "tp": tp if tp is not None else old_values["tp"],
        }

        response = {
            "success": success,
            "ticket": getattr(result, "order", order_id),
            "retcode": result.retcode,
            "comment": getattr(result, "comment", ""),
            "old_values": old_values,
            "new_values": new_values,
        }

        if success:
            logging.info(f"[MT5] modify_order SUCCESS: ticket={order_id}, price={old_values['price']:.5f}→{new_values['price']:.5f}, sl={old_values['sl']:.5f}→{new_values['sl']:.5f}, tp={old_values['tp']:.5f}→{new_values['tp']:.5f}")
        else:
            logging.warning(f"[MT5] modify_order FAILED: retcode={result.retcode}, comment={response['comment']}")

        return response


    def cancel_order(self, order_id: int) -> dict[str, Any]:
        """Cancel (remove) active pending order.
        
        Args:
            order_id: Order ticket to cancel
            
        Returns:
            {"success": bool, "ticket": int, "retcode": int, "comment": str}
        """
        # Get order info
        orders = mt5.orders_get(ticket=order_id)
        if orders is None or len(orders) == 0:
            logging.error(f"[MT5] cancel_order: order {order_id} not found: {mt5.last_error()}")
            return {"success": False, "ticket": 0, "retcode": -1, "comment": "Order not found"}

        order = orders[0]

        # Build request
        request = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": order_id,
            "symbol": order.symbol,
            "comment": "[TradingBot] canceled",
        }

        # Send cancellation
        result = mt5.order_send(request)
        if result is None:
            logging.error(f"[MT5] cancel_order: order_send failed: {mt5.last_error()}")
            return {"success": False, "ticket": 0, "retcode": -1, "comment": "order_send failed"}

        # Process result
        success = result.retcode == mt5.TRADE_RETCODE_DONE
        response = {
            "success": success,
            "ticket": getattr(result, "order", order_id),
            "retcode": result.retcode,
            "comment": getattr(result, "comment", ""),
        }

        if success:
            logging.info(f"[MT5] cancel_order SUCCESS: ticket={order_id}")
        else:
            logging.warning(f"[MT5] cancel_order FAILED: retcode={result.retcode}, comment={response['comment']}")

        return response


    def close_position(self, position_id: str, lots: float | None = None) -> str:
        """Закрытие позиции полностью или частично. Возвращает deal_id.

        TODO: Реализовать метод закрытия открытой позиции через TRADE_ACTION_DEAL.
        Требуется: получение информации о позиции, расчет объема, выставление market order.
        """
        logging.info(f"[MT5] close_position(position_id={position_id}, lots={lots})")
        return "deal_0001"


    def get_positions(self) -> list[dict[str, Any]]:
        """Получение списка открытых позиций.

        TODO: Реализовать метод получения активных позиций через mt5.positions_get().
        Требуется: парсинг структуры TradePosition, преобразование в словари.
        """
        logging.debug("[MT5] get_positions()")
        return []


    def get_orders(self) -> list[dict[str, Any]]:
        """Get list of all active pending orders.
        
        Returns list of pending orders (BUY_LIMIT, SELL_LIMIT, BUY_STOP, SELL_STOP).
        Does NOT include executed deals - use get_history() for that.
        
        Returns:
            [{"ticket": int, "symbol": str, "type": str, "volume": float,
              "price": float, "sl": float, "tp": float, "time_setup": datetime,
              "comment": str, "magic": int}, ...]
            Empty list if no orders or error.
        """
        orders = mt5.orders_get()
        
        if orders is None:
            logging.error(f"[MT5] get_orders failed: {mt5.last_error()}")
            return []
        
        if len(orders) == 0:
            return []
        
        # Map order types to readable names
        type_names = {
            mt5.ORDER_TYPE_BUY_LIMIT: "buy_limit",
            mt5.ORDER_TYPE_SELL_LIMIT: "sell_limit",
            mt5.ORDER_TYPE_BUY_STOP: "buy_stop",
            mt5.ORDER_TYPE_SELL_STOP: "sell_stop",
        }
        
        result = []
        for order in orders:
            result.append({
                "ticket": order.ticket,
                "symbol": order.symbol,
                "type": type_names.get(order.type, f"unknown_{order.type}"),
                "volume": getattr(order, "volume_initial", 0.0),
                "price": order.price_open,
                "sl": order.sl,
                "tp": order.tp,
                "time_setup": datetime.fromtimestamp(order.time_setup),
                "comment": getattr(order, "comment", ""),
                "magic": getattr(order, "magic", 0),
            })
        
        return result


    def get_history(self, since: str | None = None, until: str | None = None) -> list[dict[str, Any]]:
        """Получение истории сделок/ордеров за указанный период.

        TODO: Реализовать метод получения истории сделок через mt5.history_deals_get().
        Требуется: парсинг дат (since/until), фильтрация по периоду, преобразование в словари.
        """
        logging.debug(f"[MT5] get_history(since={since}, until={until})")
        return []


    def get_portfolio(self) -> dict[str, Any]:
        """Получение метрик портфеля: баланс/эквити/маржа.

        TODO: Реализовать метод получения портфельных метрик через mt5.account_info().
        Требуется: расчет свободной маржи, уровня маржи, других показателей риска.
        """
        logging.debug("[MT5] get_portfolio()")
        return {"balance": 0.0, "equity": 0.0, "margin": 0.0, "free_margin": 0.0}


    def get_symbol_info(self, symbol: str) -> dict[str, Any]:
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
        try:
            # Get symbol info from MT5
            si = mt5.symbol_info(symbol)
            if si is None:
                logging.error(f"[MT5] get_symbol_info failed: {mt5.last_error()}")
                return {}

            # Get current tick for bid/ask
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                logging.debug(f"[MT5] get_symbol_info: could not get tick for {symbol}")
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

            logging.debug(
                f"[MT5] get_symbol_info: {symbol} contract_size={si.trade_contract_size} min_lot={si.volume_min}"
            )
            return result

        except Exception as e:
            logging.exception(f"[MT5] get_symbol_info: exception: {e}")
            return {}


    def eur_to_lots(self, amount_eur: float, symbol: str) -> float:
        """Convert EUR amount to lots for symbol.
        
        Returns 0 if conversion fails.
        """
        # Get EUR/USD rate
        eurusd_tick = self.get_tick("EURUSD")
        if not eurusd_tick:
            logging.error("[MT5] eur_to_lots: could not get EURUSD rate")
            return 0.0

        # Convert EUR to USD
        amount_usd = amount_eur * eurusd_tick["bid"]

        # Get symbol info
        sym_info = self.get_symbol_info(symbol)
        if not sym_info:
            logging.error(f"[MT5] eur_to_lots: could not get info for {symbol}")
            return 0.0

        # Calculate and round lots
        lots = amount_usd / sym_info["contract_size"]
        lots = self._round_to_step(lots, sym_info["lot_step"])

        if lots < sym_info["min_lot"]:
            logging.warning(f"[MT5] eur_to_lots: {lots} below min_lot {sym_info['min_lot']}")
            return 0.0

        return lots


    def usd_to_lots(self, amount_usd: float, symbol: str) -> float:
        """Convert USD amount to lots for symbol.
        
        Returns 0 if conversion fails.
        """
        # Get symbol info
        sym_info = self.get_symbol_info(symbol)
        if not sym_info:
            logging.error(f"[MT5] usd_to_lots: could not get info for {symbol}")
            return 0.0

        # Calculate and round lots
        lots = amount_usd / sym_info["contract_size"]
        lots = self._round_to_step(lots, sym_info["lot_step"])

        if lots < sym_info["min_lot"]:
            logging.warning(f"[MT5] usd_to_lots: {lots} below min_lot {sym_info['min_lot']}")
            return 0.0

        return lots


    def _round_to_step(self, value: float, step: float) -> float:
        """Round value to closest multiple of step using Decimal."""
        v = Decimal(str(value))
        s = Decimal(str(step))
        if s == 0:
            return float(v)
        q = (v / s).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return float(q * s)
