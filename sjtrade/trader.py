from dataclasses import dataclass, field
from re import L
from typing import Dict, List
import shioaji as sj

from .utils import price_round
from loguru import logger
from shioaji.constant import (
    Action,
    TFTStockPriceType,
    TFTOrderType,
    QuoteVersion,
    Exchange,
)


@dataclass
class Position:
    contract: sj.contracts.Contract
    quantity: int
    stop_loss_price: float
    stop_profit_price: float
    entry_trades: List[sj.order.Trade] = field(default_factory=list)
    cancel_quantity: int = 0
    entry_quantity: int = 0
    open_quantity: int = 0
    cover_quantity: int = 0


class SJTrader:
    def __init__(self, api: sj.Shioaji):
        self.api = api
        self.positions = {}
        self._stop_loss_pct = 0.09
        self._stop_profit_pct = 0.09
        self.open_price = {}
        # self.account = api.stock_account
        # self.entry_trades: Dict[str, sj.order.Trade] = {}

    def start(self):
        pass

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

    def place_entry_order(
        self, position: Dict[str, int], pct: float
    ) -> List[sj.order.Trade]:
        trades = []
        for code, pos in position.items():
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
                self.positions[code] = dict(
                    contract=contract,
                    quantity=position[code],
                    stop_loss_price=price_round(stop_loss_price, pos > 0),
                    stop_profit_price=price_round(stop_profit_price, pos < 0),
                    cancel_quantity=0,
                    entry_quantity=0,
                    cover_quantity=0,
                )
                self.api.quote.subscribe(contract, version=QuoteVersion.v1)
                # TODO over 499 need handle
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
                    ),
                )
                trades.append(trade)
                self.positions[code]["entry_trades"] = [
                    trade,
                ]
        return trades
    

    def cancel_preorder_handler(self, exchange: Exchange, tick: sj.TickSTKv1):
        position = self.positions[tick.code]
        contract = position["contract"]
        # 8:55 - 8:59:55
        if tick.simtrade:
            if position["quantity"] < 0 and tick.close == contract.limit_up:
                for trade in self.positions[tick.code]["entry_trades"]:
                    if trade.status.status != sj.order.Status.Cancelled:
                        self.api.cancel_order(trade)
                        self.update_status(trade)
                        if trade.status.status == sj.order.Status.Cancelled:
                            position["cancel_quantity"] -= trade.status.cancel_quantity
                        else:
                            logger.warning("position {} not cancel....")
                            # TODO handel it
    
    def re_entry_order(self, exchange: Exchange, tick: sj.TickSTKv1):
        position = self.positions[tick.code]
        contract = position["contract"]
    
        # 9:00 -> first
        if not tick.simtrade:
            if tick.code not in self.open_price:
                self.open_price[tick.code] = tick.close
                if tick.close < position["stop_loss_price"]:
                    trade = self.api.place_order(
                        contract=contract,
                        order=sj.Order(
                            price=0,
                            quantity=abs(position["quantity"]),
                            action=Action.Buy
                            if position["quantity"] > 0
                            else Action.Sell,
                            price_type=TFTStockPriceType.MKT,
                            order_type=TFTOrderType.ROD,
                        ),
                    )
                    self.update_status(trade)

    def intraday_handler(self, exchange: Exchange, tick: sj.TickSTKv1):
        position = self.positions[tick.code]
        # 9:00 -> 13:24:49 stop loss stop profit
        if not tick.simtrade:
            if (
                position["open_quantity"] > 0
                and tick.close <= position["stop_loss_price"]
            ):
                self.place_cover_order(position)

            if (
                position["open_quantity"] < 0
                and tick.close >= position["stop_loss_price"]
            ):
                self.place_cover_order(position)

            if (
                position["open_quantity"] > 0
                and tick.close >= position["stop_profit_price"]
            ):
                self.place_cover_order(position)

            if (
                position["open_quantity"] < 0
                and tick.close <= position["stop_profit_price"]
            ):
                self.place_cover_order(position)

        # 13:26 place cover order
        self.open_position_cover()

    def place_cover_order(self, position):
        pass
    
    def open_position_cover(self):
        pass

    def update_status(self, trade: sj.order.Trade) -> sj.order.Trade:
        self.api._solace.update_status(trade.order.account, seqno=trade.status.seqno)
        return trade
