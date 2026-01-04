from __future__ import annotations
from typing import Any, Dict
import os


class AlertService:
    """
    Telegram-уведомления:
    - send_signal
    - send_order_update
    - send_risk_alert
    - send_error
    """

    def __init__(self, enabled: bool = True, bot_token: str | None = None, chat_id: str | None = None):
        self.enabled = enabled
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")

    def _send(self, text: str):
        if not self.enabled:
            return
        # TODO: реализовать отправку через aiogram/requests
        print(f"[TELEGRAM] {text}")

    def send_signal(self, signal: Dict[str, Any]):
        self._send(f"Signal: {signal}")

    def send_order_update(self, order_id: str, status: str):
        self._send(f"Order {order_id}: {status}")

    def send_risk_alert(self, message: str):
        self._send(f"Risk: {message}")

    def send_error(self, error: str):
        self._send(f"Error: {error}")