from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Literal, Dict, Any


Side = Literal["buy", "sell"]
OrderType = Literal["market", "limit", "stop"]


@dataclass
class Signal:
    symbol: str
    side: Side
    price: float
    sl: Optional[float]
    tp: Optional[float]
    confidence: float
    metadata: Dict[str, Any] | None = None


@dataclass
class ExitSignal:
    symbol: str
    action: Literal["close", "partial"]
    reason: str
    lots: Optional[float] = None
    metadata: Dict[str, Any] | None = None


@dataclass
class Order:
    order_id: str
    symbol: str
    side: Side
    type: OrderType
    price: Optional[float]
    lots: float
    sl: Optional[float]
    tp: Optional[float]
    status: Literal["NEW", "PLACED", "FILLED", "PARTIALLY_FILLED", "CANCELLED", "REJECTED", "EXPIRED", "CLOSED"]


@dataclass
class Position:
    position_id: str
    symbol: str
    side: Side
    entry_price: float
    lots: float
    sl: Optional[float]
    tp: Optional[float]
