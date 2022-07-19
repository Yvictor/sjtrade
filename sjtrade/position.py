import shioaji as sj
from typing import List
from threading import Lock
from dataclasses import dataclass, field
from shioaji.constant import (
    TFTStockPriceType,
)


@dataclass
class PriceSet:
    price: float
    quantity: int
    price_type: TFTStockPriceType
    in_transit_quantity: int = 0
    # time: datetime.time
    # time_cond: TimeCond


@dataclass
class PositionCond:
    quantity: int
    entry_price: List[PriceSet]
    stop_loss_price: List[PriceSet]
    stop_profit_price: List[PriceSet]
    cover_price: List[PriceSet] = field(default_factory=list)


@dataclass
class PositionStatus:
    cancel_preorder: bool = False
    cancel_quantity: int = 0
    entry_order_quantity: int = 0
    entry_quantity: int = 0
    open_quantity: int = 0
    cover_order_quantity: int = 0
    cover_quantity: int = 0


@dataclass
class Position:
    contract: sj.contracts.Contract
    cond: PositionCond
    status: PositionStatus = field(default_factory=PositionStatus)
    entry_trades: List[sj.order.Trade] = field(default_factory=list)
    cover_trades: List[sj.order.Trade] = field(default_factory=list)
    lock: Lock = field(default_factory=Lock)
