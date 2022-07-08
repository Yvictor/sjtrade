import time
import random
import datetime
from typing import Callable, Dict
from dataclasses import dataclass
from threading import Lock
from concurrent.futures import ThreadPoolExecutor
import xxhash
import shioaji as sj
from shioaji.constant import OrderState, Exchange, Action, TFTStockPriceType

from .data import Snapshot


class SimulationShioaji:
    def __init__(self, order_deal_handler: Callable[[OrderState, Dict], None]):
        self.order_callback = order_deal_handler
        self.executor = ThreadPoolExecutor(max_workers=24)
        self.use_chars = (
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
        )
        self.seqno_counter = 0
        self.snapshots: Dict[str, Snapshot] = {}
        self.lmt_price_trades: Dict[str, Dict[str, sj.order.Trade]] = {}
        self.lock = Lock()

    def quote_callback(self, exchange: Exchange, tick: sj.TickSTKv1):
        if not tick.simtrade:
            if tick.code in self.snapshots:
                s = self.snapshots[tick.code]
                s.price = tick.close
            else:
                self.snapshots[tick.code] = Snapshot(tick.close)
            with self.lock:
                if tick.code in self.lmt_price_trades:
                    lmt_price_trades = self.lmt_price_trades[tick.code]
                    pop_order_ids = []
                    for order_id, trade in lmt_price_trades.items():
                        if (
                            trade.order.action == Action.Buy
                            and tick.close <= trade.order.price
                        ) or (
                            trade.order.action == Action.Sell
                            and tick.close >= trade.order.price
                        ):
                            deal_msg = self.gen_deal_msg(
                                trade,
                                quantity=trade.order.quantity,
                                price=tick.close,
                            )
                            self.order_callback(OrderState.TFTDeal, deal_msg)
                            pop_order_ids.append(order_id)
                    for order_id in pop_order_ids:
                        self.lmt_price_trades[tick.code].pop(order_id)
                    if not lmt_price_trades:
                        self.lmt_price_trades.pop(tick.code)

    def place_order(
        self,
        contract: sj.contracts.Contract,
        order: sj.order.TFTStockOrder,
        timeout: int = 5000,
    ):
        trade = sj.order.Trade(
            contract,
            order,
            sj.order.OrderStatus(status=sj.order.Status.PreSubmitted),
        )
        future = self.executor.submit(self.call_order_callback, trade, "New")
        # future.result()
        return trade

    def cancel_order(self, trade: sj.order.Trade, timeout: int = 5000):
        future = self.executor.submit(self.call_order_callback, trade, "Cancel")
        future.result()
        return trade

    def update_status(
        self,
        account: sj.Account = None,
        trade: sj.order.Trade = None,
        timeout: int = 5000,
    ):
        pass

    def gen_order_msg(self, trade: sj.order.Trade, op_type: str):
        if op_type == "New":
            self.seqno_counter += 1
            trade.order.seqno = f"{self.seqno_counter:0>6}"
            trade.order.id = xxhash.xxh32_hexdigest(trade.order.seqno)
            trade.order.ordno = ("").join(random.sample(self.use_chars, 5))
            trade.status.status = sj.order.Status.Submitted
            op_code = "00"
        elif op_type == "Cancel":
            if trade.status.status == sj.order.Status.Filled:
                op_code = "11"
                cancel_quantity = 0
            else:
                op_code = "00"
                cancel_quantity = trade.order.quantity
                if trade.contract.code in self.lmt_price_trades:
                    trades = self.lmt_price_trades[trade.contract.code]
                    if trade.order.id in trades:
                        trades.pop(trade.order.id)
                    if not trades:
                        self.lmt_price_trades.pop(trade.contract.code)
                trade.status.status = sj.order.Status.Cancelled
        return {
            "operation": {"op_type": op_type, "op_code": op_code, "op_msg": ""},
            "order": {
                "id": trade.order.id,
                "seqno": trade.order.seqno,
                "ordno": trade.order.ordno,
                "action": trade.order.action,
                "price": trade.order.price,
                "quantity": trade.order.quantity,
                "order_cond": trade.order.order_cond,
                "order_lot": trade.order.order_lot,
                "custom_field": trade.order.custom_field,
                "order_type": trade.order.order_type,
                "price_type": trade.order.price_type,
            },
            "status": {
                "id": trade.order.id,
                "exchange_ts": datetime.datetime.now().timestamp(),
                "order_quantity": trade.order.quantity if op_type == "New" else 0,
                "modified_price": 0.0,
                "cancel_quantity": cancel_quantity if op_type == "Cancel" else 0,
                "web_id": "137",
            },
            "contract": {
                "security_type": trade.contract.security_type,
                "exchange": trade.contract.exchange,
                "code": trade.contract.code,
                "symbol": trade.contract.symbol,
                "name": trade.contract.name,
                "currency": trade.contract.currency,
            },
        }

    def gen_deal_msg(self, trade: sj.order.Trade, quantity: int, price: float):
        trade.status.deal_quantity += quantity
        trade.status.status = (
            sj.order.Status.Filled
            if quantity == trade.order.quantity
            else sj.order.Status.PartFilled
        )
        return {
            "trade_id": "12ab3456",
            "exchange_seq": "123456",
            "broker_id": "your_broker_id",
            "account_id": "your_account_id",
            "action": trade.order.action,
            "code": trade.contract.code,
            "order_cond": trade.order.order_cond,
            "order_lot": trade.order.order_lot,
            "price": price,
            "quantity": quantity,
            "web_id": "137",
            "custom_field": trade.order.custom_field,
            "ts": datetime.datetime.now().timestamp(),
        }

    def call_order_callback(self, trade: sj.order.Trade, op_type: str):
        time.sleep(0.5)
        order_msg = self.gen_order_msg(trade, op_type)
        self.order_callback(OrderState.TFTOrder, order_msg)
        time.sleep(0.1)
        if trade.order.price_type == TFTStockPriceType.MKT:
            if trade.status.status != sj.order.Status.Cancelled:
                s = self.snapshots.get(trade.contract.code)
                deal_msg = self.gen_deal_msg(
                    trade,
                    quantity=trade.order.quantity,
                    price=s.price if s else trade.order.price,
                )
                self.order_callback(OrderState.TFTDeal, deal_msg)
        else:
            if trade.status.status != sj.order.Status.Cancelled:
                with self.lock:
                    if trade.contract.code in self.lmt_price_trades:
                        self.lmt_price_trades[trade.contract.code][
                            trade.order.id
                        ] = trade
                    else:
                        self.lmt_price_trades[trade.contract.code] = {
                            trade.order.id: trade
                        }
