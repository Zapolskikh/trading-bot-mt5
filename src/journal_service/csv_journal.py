from __future__ import annotations
import csv
import os
from typing import Dict, Any
from datetime import datetime


class JournalService:
    """
    CSV-журналы: trades.csv, orders.csv, signals.csv
    """

    def __init__(self, base_path: str = "./journal", rotate_daily: bool = True):
        self.base_path = base_path
        self.rotate_daily = rotate_daily
        os.makedirs(self.base_path, exist_ok=True)

    def _file(self, name: str) -> str:
        if self.rotate_daily:
            date = datetime.utcnow().strftime("%Y-%m-%d")
            return os.path.join(self.base_path, f"{name}_{date}.csv")
        return os.path.join(self.base_path, f"{name}.csv")

    def append(self, name: str, row: Dict[str, Any]):
        path = self._file(name)
        exists = os.path.exists(path)
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(row.keys()))
            if not exists:
                writer.writeheader()
            writer.writerow(row)

    def log_signal(self, **kwargs):
        self.append("signals", kwargs)

    def log_order(self, **kwargs):
        self.append("orders", kwargs)

    def log_trade(self, **kwargs):
        self.append("trades", kwargs)
