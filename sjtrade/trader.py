from dataclasses import dataclass, field
from typing import Dict, List
from threading import Lock
import shioaji as sj

from .utils import price_round, sleep_until
from .io.file import read_position
from loguru import logger
from shioaji.constant import (
    Action,
    TFTStockPriceType,
    TFTOrderType,
    QuoteVersion,
    Exchange,
    OrderState,
)


@dataclass
class Position:
    contract: sj.contracts.Contract
    quantity: int
    stop_loss_price: float
    stop_profit_price: float
    entry_trades: List[sj.order.Trade] = field(default_factory=list)
    cover_trades: List[sj.order.Trade] = field(default_factory=list)
    cancel_preorder: bool = False
    cancel_quantity: int = 0
    entry_order_quantity: int = 0
    entry_quantity: int = 0
    open_quantity: int = 0
    cover_order_quantity: int = 0
    cover_quantity: int = 0
    lock: Lock = field(default_factory=Lock)


class SJTrader:
    def __init__(self, api: sj.Shioaji):
        self.api = api
        self.positions: Dict[str, Position] = {}
        self._stop_loss_pct = 0.09
        self._stop_profit_pct = 0.09
        self._entry_pct = 0.05
        self.open_price = {}
        self._position_filepath = "position.txt"
        self.name = "dt1"
        # self.account = api.stock_account
        # self.entry_trades: Dict[str, sj.order.Trade] = {}

    def start(self):
        positions = read_position(self._position_filepath)
        self.api.set_order_callback(self.order_deal_handler)
        sleep_until(8, 45)
        self.place_entry_order(positions, self.entry_pct)
        sleep_until(8, 54, 59)
        self.api.quote.set_on_tick_stk_v1_callback(self.cancel_preorder_handler)
        sleep_until(8, 59, 55)
        self.api.quote.set_on_tick_stk_v1_callback(self.intraday_handler)
        sleep_until(13, 25, 59)
        self.open_position_cover()

    @property
    def stop_loss_pct(self) -> float:
        return self._stop_loss_pct

    @stop_loss_pct.setter
    def stop_loss_pct(self, v: float) -> float:
        self._stop_loss_pct = v

    @property
    def stop_profit_pct(self) -> float:
        return self._stop_profit_pct

    @stop_profit_pct.setter
    def stop_profit_pct(self, v: float) -> float:
        self._stop_profit_pct = v

    @property
    def entry_pct(self) -> float:
        return self._entry_pct

    @entry_pct.setter
    def entry_pct(self, v: float) -> float:
        self._entry_pct = v

    @property
    def position_filepath(self) -> float:
        return self._position_filepath

    @position_filepath.setter
    def position_filepath(self, v: str) -> float:
        self._position_filepath = v

    def place_entry_order(
        self, positions: Dict[str, int], pct: float
    ) -> List[sj.order.Trade]:
        trades = []
        for code, pos in positions.items():
            contract = self.api.Contracts.Stocks[code]
            if not contract:
                logger.warning(f"Code: {code} not exist in TW Stock.")
            else:
                # TODO abstract func
                stop_loss_price = contract.reference * (
                    1 + (-1 if pos > 0 else 1) * (self._stop_loss_pct)
                )
                stop_profit_price = contract.reference * (
                    1 + (1 if pos > 0 else -1) * (self._stop_profit_pct)
                )
                self.positions[code] = Position(
                    contract=contract,
                    quantity=positions[code],
                    stop_loss_price=price_round(stop_loss_price, pos > 0),
                    stop_profit_price=price_round(stop_profit_price, pos < 0),
                )
                self.api.quote.subscribe(contract, version=QuoteVersion.v1)
                # TODO over 499 need handle
                with self.positions[code].lock:
                    trade = self.api.place_order(
                        contract=self.api.Contracts.Stocks[code],
                        order=sj.Order(
                            price=price_round(
                                self.api.Contracts.Stocks[code].reference * pct, pos > 0
                            ),
                            quantity=abs(pos),
                            action=Action.Buy if pos > 0 else Action.Sell,
                            price_type=TFTStockPriceType.LMT,
                            order_type=TFTOrderType.ROD,
                            custom_field=self.name,
                        ),
                    )
                    trades.append(trade)
                    self.positions[code].entry_trades.append(trade)
                    # self.positions[code]["entry_order_quantity"] = pos
        self.api.update_status()
        return trades

    def cancel_preorder_handler(self, exchange: Exchange, tick: sj.TickSTKv1):
        position = self.positions[tick.code]
        # 8:55 - 8:59:55
        if tick.simtrade:
            if position.quantity < 0 and tick.close == position.contract.limit_up:
                with position.lock:
                    position.cancel_preorder = True
                for trade in self.positions[tick.code].entry_trades:
                    if trade.status.status != sj.order.Status.Cancelled:
                        self.api.cancel_order(trade)
                        # check handle
                        # self.update_status(trade)
                        # if trade.status.status == sj.order.Status.Cancelled:
                        #     position.cancel_preorder = True
                        # else:
                        #     logger.warning("position {} not cancel....")
                        # TODO handel it

    def re_entry_order(self, position: Position, tick: sj.TickSTKv1):
        # 9:00 -> first
        if not tick.simtrade:
            if tick.code not in self.open_price:
                self.open_price[tick.code] = tick.close
                if position.cancel_preorder and tick.close < position.stop_loss_price:
                    trade = self.api.place_order(
                        contract=position.contract,
                        order=sj.order.TFTStockOrder(
                            price=0,
                            quantity=abs(position.quantity),
                            action=Action.Buy if position.quantity > 0 else Action.Sell,
                            price_type=TFTStockPriceType.MKT,
                            order_type=TFTOrderType.ROD,
                        ),
                    )
                    self.update_status(trade)

    def intraday_handler(self, exchange: Exchange, tick: sj.TickSTKv1):
        position = self.positions[tick.code]
        self.re_entry_order(position, tick)
        # 9:00 -> 13:24:49 stop loss stop profit
        self.stop_loss(position, tick)
        self.stop_profit(position, tick)

    def stop_profit(self, position: Position, tick: sj.TickSTKv1):
        if not tick.simtrade:
            if position.open_quantity > 0 and tick.close >= position.stop_profit_price:
                self.place_cover_order(position)

            if position.open_quantity < 0 and tick.close <= position.stop_profit_price:
                self.place_cover_order(position)

    def stop_loss(self, position: Position, tick: sj.TickSTKv1):
        if not tick.simtrade:
            if position.open_quantity > 0 and tick.close <= position.stop_loss_price:
                self.place_cover_order(position)

            if position.open_quantity < 0 and tick.close >= position.stop_loss_price:
                self.place_cover_order(position)

    def place_cover_order(self, position: Position, with_price: bool = False):
        if position.open_quantity + position.cover_order_quantity:
            action = (
                Action.Buy
                if position.open_quantity + position.cover_order_quantity < 0
                else Action.Sell
            )
            trade = self.api.place_order(
                contract=position.contract,
                order=sj.order.TFTStockOrder(
                    price=(
                        position.contract.limit_down
                        if action == Action.Buy
                        else position.contract.limit_up
                    )
                    if with_price
                    else 0,
                    quantity=abs(
                        position.open_quantity + position.cover_order_quantity
                    ),
                    action=action,
                    price_type=TFTStockPriceType.LMT
                    if with_price
                    else TFTStockPriceType.MKT,
                    order_type=TFTOrderType.ROD,
                ),
            )
            self.update_status(trade)
            position.cover_trades.append(trade)

    def open_position_cover(self):
        self.api.update_status()
        for code, position in self.positions.items():
            if position.cover_order_quantity:
                for trade in position.cover_trades:
                    self.api.cancel_order(trade)
            # event wait cancel
            self.place_cover_order(position, with_price=True)

    def order_deal_handler(self, order_stats: OrderState, msg: Dict):
        if (
            order_stats == OrderState.TFTOrder
            and msg["order"]["custom_field"] == self.name
        ):
            self.order_handler(msg, self.positions[msg["contract"]["code"]])
        elif order_stats == OrderState.TFTDeal and msg["custom_field"] == self.name:
            self.deal_handler(msg, self.positions[msg["code"]])

    def order_handler(self, msg: Dict, position: Position):
        if msg["operation"]["op_code"] == "00":
            with position.lock:
                if msg["operation"]["op_type"] == "New":
                    order_quantity = msg["status"].get("order_quantity", 0)
                    if msg["order"]["action"] == Action.Sell:
                        if position.quantity < 0:
                            position.entry_order_quantity -= order_quantity
                        else:
                            position.cover_order_quantity -= order_quantity
                    else:
                        if position.quantity < 0:
                            position.cover_order_quantity += order_quantity
                        else:
                            position.entry_order_quantity += order_quantity
                else:
                    cancel_quantity = msg["status"].get("cancel_quantity", 0)
                    if msg["order"]["action"] == Action.Sell:
                        if position.quantity < 0:
                            position.entry_order_quantity += cancel_quantity
                        else:
                            position.cover_order_quantity += cancel_quantity
                    else:
                        if position.quantity < 0:
                            position.cover_order_quantity -= cancel_quantity
                        else:
                            position.entry_order_quantity -= cancel_quantity
                    position.cancel_quantity += cancel_quantity
        else:
            logger.error(f"Please Check: {msg}")

    def deal_handler(self, msg: Dict, position: Position):
        with position.lock:
            if msg["action"] == Action.Sell:
                position.open_quantity -= msg["quantity"]
                if position.quantity < 0:
                    position.entry_quantity -= msg["quantity"]
                else:
                    position.cover_quantity -= msg["quantity"]
            else:
                position.open_quantity += msg["quantity"]
                if position.quantity < 0:
                    position.cover_quantity += msg["quantity"]
                else:
                    position.entry_quantity += msg["quantity"]

    def update_status(self, trade: sj.order.Trade) -> sj.order.Trade:
        self.api._solace.update_status(trade.order.account, seqno=trade.order.seqno)
        return trade
