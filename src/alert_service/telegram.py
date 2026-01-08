from __future__ import annotations
import logging
from typing import Any, Dict
import os

import requests


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
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")

    def _send(self, text: str) -> bool:
        """
        Sends a text message to a Telegram channel or chat using the requests library.

        Args:
            bot_token (str): The Telegram bot token obtained from BotFather.
            chat_id (str): The chat ID or channel username (e.g., "@channelusername").
            message (str): The text message to send.
        """
        if not self.enabled:
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": f"{text}", "parse_mode": "Markdown"}

        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            logging.info("The message was sent successfully.")
            return True
        except Exception as e:
            logging.error(f"Error occurred while sending message: {e}")
            return False

    def send_signal(self, signal: Dict[str, Any]):
        message = self.format_dict_markdown({"Signal": signal})
        self._send(message)

    def send_order_update(self, order_id: str, status: str):
        message = self.format_dict_markdown({f"Order {order_id}": {"status": status}})
        self._send(message)

    def send_risk_alert(self, message: str):
        message = self.format_dict_markdown({"Risk": {"message": message}})
        self._send(message)

    def send_error(self, error: str):
        message = self.format_dict_markdown({"Error": {"message": error}})
        self._send(message)

    @staticmethod
    def format_dict_markdown(data: dict[str, dict[str, Any]]) -> str:
        formatted_message = ""
        for key, value in data.items():
            formatted_message += f"*{key}:*\n"
            formatted_message += f'{"-" * 50}\n'

            for subkey, subvalue in value.items():
                if isinstance(subvalue, list):
                    formatted_message += f"*{subkey}:*\n\n"
                    for event in subvalue:
                        event_value = event["actual"] or event["forecast"]
                        formatted_message += (
                            f'{event["market_reaction"]}`[{event["time"]}]` {event["event_name"]}: `{event_value} (prev'
                            f' {event["previous"]})`\n'
                        )
                else:
                    formatted_message += f"*{subkey}:* `{subvalue}`\n"
            formatted_message += "\n\n"
        return formatted_message


if __name__ == "__main__":
    # ONLY for debug and testing setup
    from dotenv import load_dotenv

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    load_dotenv(".env")

    tg_alerts = AlertService()
    tg_alerts.send_signal({"symbol": "APPL", "price": 245, "sl": 240, "action": "buy", "tp": 250})
