import time
import random
import datetime
from dataclasses import dataclass, field
from typing import Callable, Dict, List
from threading import Lock
from concurrent.futures import ThreadPoolExecutor
import xxhash
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
    StockFirstSell,
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


@dataclass
class Snapshot:
    price: float
    bid: float = 0
    ask: float = 0


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
        self, contract: sj.contracts.Contract, order: sj.order.TFTStockOrder
    ):
        trade = sj.order.Trade(
            contract,
            order,
            sj.order.OrderStatus(status=sj.order.Status.PreSubmitted),
        )
        future = self.executor.submit(self.call_order_callback, trade, "New")
        # future.result()
        return trade

    def cancel_order(self, trade: sj.order.Trade):
        future = self.executor.submit(self.call_order_callback, trade, "Cancel")
        future.result()
        return trade

    def update_status(self, account: sj.Account = None, trade: sj.order.Trade = None):
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
                        self.lmt_price_trades[trade.contract.code][trade.order.id] = trade
                    else:
                        self.lmt_price_trades[trade.contract.code] = {trade.order.id: trade}


class SJTrader:
    def __init__(self, api: sj.Shioaji, simulation: bool = False):
        self.api = api
        self.positions: Dict[str, Position] = {}
        self._stop_loss_pct = 0.09
        self._stop_profit_pct = 0.09
        self._entry_pct = 0.05
        self.open_price = {}
        self._position_filepath = "position.txt"
        self.name = "dt1"
        self.simulation = simulation
        if simulation:
            self.simulation_api = SimulationShioaji(self.order_deal_handler)
        self.api.quote.set_event_callback(self.sj_event_handel)
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

    def sj_event_handel(self, resp_code: int, event_code: int, info: str, event: str):
        logger.info(
            f"Response Code: {resp_code} | Event Code: {event_code} | Info: {info} | Event: {event}"
        )

    def place_entry_order(
        self, positions: Dict[str, int], pct: float
    ) -> List[sj.order.Trade]:
        trades = []
        if self.simulation:
            api = self.simulation_api
        else:
            api = self.api
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
                    trade = api.place_order(
                        contract=self.api.Contracts.Stocks[code],
                        order=sj.Order(
                            price=price_round(
                                self.api.Contracts.Stocks[code].reference * pct,
                                pos > 0,
                            ),
                            quantity=abs(pos),
                            action=Action.Buy if pos > 0 else Action.Sell,
                            price_type=TFTStockPriceType.LMT,
                            order_type=TFTOrderType.ROD,
                            first_sell=StockFirstSell.No
                            if pos > 0
                            else StockFirstSell.Yes,
                            custom_field=self.name,
                        ),
                    )
                    trades.append(trade)
                    self.positions[code].entry_trades.append(trade)
                    logger.info(f"{code}, {trade.order}")
                    # self.positions[code]["entry_order_quantity"] = pos
        api.update_status()
        return trades

    def cancel_preorder_handler(self, exchange: Exchange, tick: sj.TickSTKv1):
        position = self.positions[tick.code]
        if self.simulation:
            api = self.simulation_api
        else:
            api = self.api
        # 8:55 - 8:59:55
        if tick.simtrade:
            if position.quantity < 0 and tick.close == position.contract.limit_up:
                with position.lock:
                    position.cancel_preorder = True
                for trade in self.positions[tick.code].entry_trades:
                    if trade.status.status != sj.order.Status.Cancelled:
                        api.cancel_order(trade)
                        logger.info(f"{trade.contract.code}, {trade.order}")
                        # check handle
                        # self.update_status(trade)
                        # if trade.status.status == sj.order.Status.Cancelled:
                        #     position.cancel_preorder = True
                        # else:
                        #     logger.warning("position {} not cancel....")
                        # TODO handel it

    def re_entry_order(self, position: Position, tick: sj.TickSTKv1):
        # 9:00 -> first
        if self.simulation:
            api = self.simulation_api
        else:
            api = self.api
        if not tick.simtrade:
            if tick.code not in self.open_price:
                self.open_price[tick.code] = tick.close
                if position.cancel_preorder and tick.close < position.stop_loss_price:
                    trade = api.place_order(
                        contract=position.contract,
                        order=sj.order.TFTStockOrder(
                            price=0,
                            quantity=abs(position.quantity),
                            action=Action.Buy if position.quantity > 0 else Action.Sell,
                            price_type=TFTStockPriceType.MKT,
                            order_type=TFTOrderType.ROD,
                            first_sell=StockFirstSell.No
                            if position.quantity > 0
                            else StockFirstSell.Yes,
                            custom_field=self.name,
                        ),
                    )
                    logger.info(f"{trade.contract.code}, {trade.order}")
                    api.update_status(trade=trade)

    def intraday_handler(self, exchange: Exchange, tick: sj.TickSTKv1):
        if self.simulation:
            self.simulation_api.quote_callback(exchange, tick)
        position = self.positions[tick.code]
        self.re_entry_order(position, tick)
        # 9:00 -> 13:24:49 stop loss stop profit
        self.stop_loss(position, tick)
        self.stop_profit(position, tick)

    def stop_profit(self, position: Position, tick: sj.TickSTKv1):
        if not tick.simtrade:
            if position.open_quantity > 0 and tick.close >= position.stop_profit_price:
                self.place_cover_order(position)
                logger.info(
                    f"{position.contract.code}, price: {tick.close} cross over {position.stop_profit_price}"
                )

            if position.open_quantity < 0 and tick.close <= position.stop_profit_price:
                self.place_cover_order(position)
                logger.info(
                    f"{position.contract.code}, price: {tick.close} cross under {position.stop_profit_price}"
                )

    def stop_loss(self, position: Position, tick: sj.TickSTKv1):
        if not tick.simtrade:
            if position.open_quantity > 0 and tick.close <= position.stop_loss_price:
                self.place_cover_order(position)
                logger.info(
                    f"{position.contract.code}, price: {tick.close} cross under {position.stop_loss_price}"
                )

            if position.open_quantity < 0 and tick.close >= position.stop_loss_price:
                self.place_cover_order(position)
                logger.info(
                    f"{position.contract.code}, price: {tick.close} cross over {position.stop_loss_price}"
                )

    def place_cover_order(self, position: Position, with_price: bool = False):
        if self.simulation:
            api = self.simulation_api
        else:
            api = self.api
        if position.open_quantity + position.cover_order_quantity:
            action = (
                Action.Buy
                if position.open_quantity + position.cover_order_quantity < 0
                else Action.Sell
            )
            trade = api.place_order(
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
                    custom_field=self.name,
                ),
            )
            logger.info(f"{trade.contract.code}, {trade.order}")
            api.update_status(trade=trade)
            position.cover_trades.append(trade)

    def open_position_cover(self):
        if self.simulation:
            api = self.simulation_api
        else:
            api = self.api
        api.update_status()
        for code, position in self.positions.items():
            if position.cover_order_quantity:
                for trade in position.cover_trades:
                    api.cancel_order(trade)
            # event wait cancel
            logger.info("start place cover order.")
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
                            logger.info(
                                f"{position.contract.code}, place entry order success with {order_quantity}"
                            )
                        else:
                            position.cover_order_quantity -= order_quantity
                            logger.info(
                                f"{position.contract.code}, place cover order success with {order_quantity}"
                            )
                    else:
                        if position.quantity < 0:
                            position.cover_order_quantity += order_quantity
                            logger.info(
                                f"{position.contract.code}, place cover order success with {order_quantity}"
                            )
                        else:
                            position.entry_order_quantity += order_quantity
                            logger.info(
                                f"{position.contract.code}, place entry order success with {order_quantity}"
                            )
                else:
                    cancel_quantity = msg["status"].get("cancel_quantity", 0)
                    if msg["order"]["action"] == Action.Sell:
                        if position.quantity < 0:
                            position.entry_order_quantity += cancel_quantity
                            logger.info(
                                f"{position.contract.code}, canel entry order success with {cancel_quantity}"
                            )
                        else:
                            position.cover_order_quantity += cancel_quantity
                            logger.info(
                                f"{position.contract.code}, canel cover order success with {cancel_quantity}"
                            )
                    else:
                        if position.quantity < 0:
                            position.cover_order_quantity -= cancel_quantity
                            logger.info(
                                f"{position.contract.code}, canel cover order success with {cancel_quantity}"
                            )
                        else:
                            position.entry_order_quantity -= cancel_quantity
                            logger.info(
                                f"{position.contract.code}, canel entry order success with {cancel_quantity}"
                            )
                    position.cancel_quantity += cancel_quantity
        else:
            logger.error(f"Please Check: {msg}")

    def deal_handler(self, msg: Dict, position: Position):
        with position.lock:
            deal_quantity = msg["quantity"]
            deal_price = msg["price"]
            if msg["action"] == Action.Sell:
                position.open_quantity -= deal_quantity
                if position.quantity < 0:
                    position.entry_quantity -= deal_quantity
                    logger.info(
                        f"{position.contract.code}, entry order deal with {deal_quantity}, price: {deal_price}"
                    )
                else:
                    position.cover_quantity -= deal_quantity
                    logger.info(
                        f"{position.contract.code}, cover order deal with {deal_quantity}, price: {deal_price}"
                    )
            else:
                position.open_quantity += deal_quantity
                if position.quantity < 0:
                    position.cover_quantity += deal_quantity
                    logger.info(
                        f"{position.contract.code}, cover order deal with {deal_quantity}, price: {deal_price}"
                    )
                else:
                    position.entry_quantity += deal_quantity
                    logger.info(
                        f"{position.contract.code}, entry order deal with {deal_quantity}, price: {deal_price}"
                    )
