import time
import datetime
import operator
from typing import Callable, Dict, List, Optional, Union
from concurrent.futures import Future, ThreadPoolExecutor
import shioaji as sj

from .utils import quantity_split, sleep_until
from .data import Snapshot
from .simulation_shioaji import SimulationShioaji
from .strategy import StrategyBasic
from .position import Position, PositionCond, PriceSet
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


logger.add("sjtrader.log", rotation="1 days")


class SJTrader:
    def __init__(self, api: sj.Shioaji, simulation: bool = False):
        self.api = api
        self.positions: Dict[str, Position] = {}
        self.snapshots: Dict[str, Snapshot] = {}
        self._stop_loss_pct = 0.09
        self._stop_profit_pct = 0.09
        self._entry_pct = 0.05
        self.open_price = {}
        self._position_filepath = "position.txt"
        self.name = "dt1"
        self.executor = ThreadPoolExecutor()
        self.simulation = simulation
        if simulation:
            self.simulation_api = SimulationShioaji(self.order_deal_handler)
        self.api.set_order_callback(self.order_deal_handler)
        self.api.quote.set_event_callback(self.sj_event_handel)
        self.stratagy = StrategyBasic(contracts=self.api.Contracts)
        # self.account = api.stock_account
        # self.entry_trades: Dict[str, sj.order.Trade] = {}

    def start(
        self,
        entry_time: datetime.time = datetime.time(8, 45),
        cancel_preorder_time: datetime.time = datetime.time(8, 54, 59),
        intraday_handler_time: datetime.time = datetime.time(8, 59, 55),
        cover_time: datetime.time = datetime.time(13, 25, 59),
    ):
        self.set_on_tick_handler(self.update_snapshot)
        entry_future = self.executor_on_time(entry_time, self.place_entry_positions)
        self.executor_on_time(
            cancel_preorder_time,
            self.set_on_tick_handler,
            self.cancel_preorder_handler,
        )
        self.executor_on_time(
            intraday_handler_time,
            self.set_on_tick_handler,
            self.intraday_handler,
        )
        self.executor_on_time(cover_time, self.open_position_cover)
        return entry_future

    def run_at(self, t: Union[datetime.time, tuple], func: Callable, *args, **kwargs):
        sleep_until(t)
        return func(*args, **kwargs)

    def executor_on_time(
        self, t: Union[datetime.time, tuple], func: Callable, *args, **kwargs
    ) -> Future:
        return self.executor.submit(self.run_at, t, func, *args, **kwargs)

    def set_on_tick_handler(self, func: Callable[[Exchange, sj.TickSTKv1], None]):
        self.api.quote.set_on_tick_stk_v1_callback(func)

    @property
    def stop_loss_pct(self) -> float:
        return self._stop_loss_pct

    @stop_loss_pct.setter
    def stop_loss_pct(self, v: float) -> float:
        self._stop_loss_pct = v
        self.stratagy.stop_loss_pct = self._stop_loss_pct

    @property
    def stop_profit_pct(self) -> float:
        return self._stop_profit_pct

    @stop_profit_pct.setter
    def stop_profit_pct(self, v: float) -> float:
        self._stop_profit_pct = v
        self.stratagy.stop_profit_pct = self._stop_profit_pct

    @property
    def entry_pct(self) -> float:
        return self._entry_pct

    @entry_pct.setter
    def entry_pct(self, v: float) -> float:
        self._entry_pct = v
        self.stratagy.entry_pct = self._entry_pct

    @property
    def position_filepath(self) -> float:
        return self._position_filepath

    @position_filepath.setter
    def position_filepath(self, v: str) -> float:
        self._position_filepath = v
        self.stratagy.position_filepath = self._position_filepath

    def sj_event_handel(self, resp_code: int, event_code: int, info: str, event: str):
        logger.info(
            f"Response Code: {resp_code} | Event Code: {event_code} | Info: {info} | Event: {event}"
        )

    def place_entry_order(
        self,
        code: str,
        pos: int,
        entry_price: List[PriceSet],
        stop_profit_price: List[PriceSet],
        stop_loss_price: List[PriceSet],
    ):
        api = self.simulation_api if self.simulation else self.api
        contract = self.api.Contracts.Stocks[code]
        if not contract:
            logger.warning(f"Code: {code} not exist in TW Stock.")
        else:
            position = self.positions[code] = Position(
                contract=contract,
                cond=PositionCond(
                    quantity=pos,
                    entry_price=entry_price,
                    stop_loss_price=stop_loss_price,
                    stop_profit_price=stop_profit_price,
                    cover_price=[],
                ),
            )
            self.snapshots[code] = Snapshot(price=0.0)
            self.api.quote.subscribe(contract, version=QuoteVersion.v1)
            for price_set in position.cond.entry_price:
                if abs(price_set.quantity) == abs(price_set.in_transit_quantity):
                    continue
                price, price_quantity = price_set.price, price_set.quantity
                quantity_s = quantity_split(price_quantity, threshold=499)
                with position.lock:
                    for q in quantity_s:
                        trade = api.place_order(
                            contract=contract,
                            order=sj.Order(
                                price=price,
                                quantity=abs(q),
                                action=Action.Buy if pos > 0 else Action.Sell,
                                price_type=price_set.price_type,
                                order_type=TFTOrderType.ROD,
                                first_sell=StockFirstSell.No
                                if pos > 0
                                else StockFirstSell.Yes,
                                custom_field=self.name,
                            ),
                            timeout=0,
                        )
                        price_set.in_transit_quantity += q
                        # position.status.entry_order_in_transit += q
                        position.entry_trades.append(trade)
                        logger.info(f"{code} | {trade.order}")

    def place_entry_positions(self) -> Dict[str, Position]:
        api = self.simulation_api if self.simulation else self.api
        for entry_kwarg in self.stratagy.entry_positions():
            self.place_entry_order(**entry_kwarg)
        api.update_status()
        return self.positions

    def update_snapshot(self, exchange: Exchange, tick: sj.TickSTKv1):
        self.snapshots[tick.code].price = tick.close

    def cancel_preorder_handler(self, exchange: Exchange, tick: sj.TickSTKv1):
        position = self.positions[tick.code]
        if self.simulation:
            api = self.simulation_api
        else:
            api = self.api
        # 8:55 - 8:59:55
        if tick.simtrade:
            if position.cond.quantity < 0 and float(tick.close) == position.contract.limit_up:
                with position.lock:
                    position.status.cancel_preorder = True
                for trade in self.positions[tick.code].entry_trades:
                    if trade.status.status != sj.order.Status.Cancelled:
                        api.cancel_order(trade, timeout=0)
                        logger.info(f"{trade.contract.code} | {trade.order}")
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
                if (
                    position.status.cancel_preorder
                    and float(tick.close) < position.cond.stop_loss_price[0].price
                ):  # TODO check min or max
                    trade = api.place_order(
                        contract=position.contract,
                        order=sj.order.TFTStockOrder(
                            price=0,
                            quantity=abs(position.cond.quantity),
                            action=Action.Buy
                            if position.cond.quantity > 0
                            else Action.Sell,
                            price_type=TFTStockPriceType.MKT,
                            order_type=TFTOrderType.ROD,
                            first_sell=StockFirstSell.No
                            if position.cond.quantity > 0
                            else StockFirstSell.Yes,
                            custom_field=self.name,
                        ),
                        timeout=0,
                    )
                    logger.info(f"{trade.contract.code} | {trade.order}")
                    api.update_status(trade=trade)

    def intraday_handler(self, exchange: Exchange, tick: sj.TickSTKv1):
        if self.simulation:
            self.simulation_api.quote_callback(exchange, tick)
        position = self.positions[tick.code]
        self.re_entry_order(position, tick)
        self.update_snapshot(exchange, tick)
        # 9:00 -> 13:24:49 stop loss stop profit
        self.stop_loss(position, tick)
        self.stop_profit(position, tick)

    def stop_profit(self, position: Position, tick: sj.TickSTKv1):
        if not tick.simtrade:
            cover_quantity = (
                position.status.open_quantity + position.status.cover_order_quantity
            )
            if cover_quantity == 0:
                return
            if position.status.open_quantity > 0:
                op = operator.ge
                cross = "over"
            else:
                op = operator.le
                cross = "under"
            for price_set in position.cond.stop_profit_price:
                if op(float(tick.close), price_set.price):
                    if abs(price_set.quantity) == abs(price_set.in_transit_quantity):
                        continue
                    self.place_cover_order(position, [price_set])
                    logger.info(
                        f"{position.contract.code} | price: {tick.close} cross {cross} {price_set.price} "
                        f"cover quantity: {price_set.quantity}"
                    )

    def stop_loss(self, position: Position, tick: sj.TickSTKv1):
        if not tick.simtrade:
            cover_quantity = (
                position.status.open_quantity + position.status.cover_order_quantity
            )
            if cover_quantity == 0:
                return
            if position.status.open_quantity > 0:
                op = operator.le
                cross = "under"
            else:
                op = operator.ge
                cross = "over"
            for price_set in position.cond.stop_loss_price:
                if op(float(tick.close), price_set.price):
                    if abs(price_set.quantity) == abs(price_set.in_transit_quantity):
                        continue
                    self.place_cover_order(position, [price_set])
                    logger.info(
                        f"{position.contract.code} | price: {tick.close} cross {cross} {price_set.price} "
                        f"cover quantity: {price_set.quantity}"
                    )

    def place_cover_order(
        self, position: Position, price_sets: List[PriceSet] = []
    ):  # TODO with price quantity
        if self.simulation:
            api = self.simulation_api
        else:
            api = self.api
        cover_quantity = (
            position.status.open_quantity + position.status.cover_order_quantity
        )
        if not price_sets:
            price_sets = self.stratagy.cover_price_set(
                position, self.snapshots[position.contract.code]
            )
            position.cond.cover_price += price_sets
        if cover_quantity == 0:
            return
        for price_set in price_sets:
            if abs(price_set.quantity) == abs(price_set.in_transit_quantity):
                continue
            if price_set.quantity:
                quantity_s = quantity_split(price_set.quantity, threshold=499)
                for q in quantity_s:
                    trade = api.place_order(
                        contract=position.contract,
                        order=sj.order.TFTStockOrder(
                            price=price_set.price,
                            quantity=abs(q),
                            action=Action.Buy
                            if position.cond.quantity < 0
                            else Action.Sell,
                            price_type=price_set.price_type,
                            order_type=TFTOrderType.ROD,
                            custom_field=self.name,
                        ),
                        timeout=0,
                    )
                    logger.info(f"{trade.contract.code} | {trade.order}")
                    price_set.in_transit_quantity += q
                    position.cover_trades.append(trade)
                    # api.update_status(trade=trade)

    def open_position_cover(self, onclose: bool = True):
        if self.simulation:
            api = self.simulation_api
        else:
            api = self.api
        api.update_status()
        logger.info(f"start place cover order. onclose: {onclose}")
        for code, position in self.positions.items():
            if position.status.cover_order_quantity and (
                position.status.cover_order_quantity != position.status.cover_quantity
            ):
                for trade in position.cover_trades:
                    if trade.status.status in [
                        sj.order.Status.Submitted,
                        sj.order.Status.PreSubmitted,
                        sj.order.Status.PartFilled,
                    ]:
                        api.cancel_order(trade, timeout=0)
            if position.status.entry_order_quantity and (
                position.status.entry_order_quantity != position.status.entry_quantity
            ):
                for trade in position.entry_trades:
                    if trade.status.status in [
                        sj.order.Status.Submitted,
                        sj.order.Status.PreSubmitted,
                        sj.order.Status.PartFilled,
                    ]:
                        api.cancel_order(trade, timeout=0)
            # event wait cancel
        for code, position in self.positions.items():
            for _ in range(10):
                if (
                    position.status.cover_quantity
                    != position.status.cover_order_quantity
                ):
                    time.sleep(1)
            if position.status.cover_quantity != position.status.cover_order_quantity:
                logger.error(
                    f"{code} | cancel not work, position cover order "
                    f"{position.status.cover_order_quantity}, position cover {position.status.cover_quantity}"
                )
        if onclose:
            self.positions = self.stratagy.cover_positions_onclose(self.positions)
        else:
            self.positions = self.stratagy.cover_positions(
                self.positions, self.snapshots
            )
        for code, position in self.positions.items():
            if position.status.open_quantity:
                self.place_cover_order(position, position.cond.cover_price)

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
                    order_pirce = msg["order"].get("price", 0)
                    if msg["order"]["action"] == Action.Sell:
                        if position.cond.quantity < 0:
                            position.status.entry_order_quantity -= order_quantity
                            logger.info(
                                f"{position.contract.code} | place short entry order with quantity {order_quantity}, price: {order_pirce}"
                            )
                            logger.debug(
                                f"{position.contract.code} | {position.status}"
                            )
                        else:
                            position.status.cover_order_quantity -= order_quantity
                            logger.info(
                                f"{position.contract.code} | place long cover order with quantity {order_quantity}, price: {order_pirce}"
                            )
                            logger.debug(
                                f"{position.contract.code} | {position.status}"
                            )
                    else:
                        if position.cond.quantity < 0:
                            position.status.cover_order_quantity += order_quantity
                            logger.info(
                                f"{position.contract.code} | place short cover order with quantity {order_quantity}, price: {order_pirce}"
                            )
                            logger.debug(
                                f"{position.contract.code} | {position.status}"
                            )
                        else:
                            position.status.entry_order_quantity += order_quantity
                            logger.info(
                                f"{position.contract.code} | place long entry order with quantity {order_quantity}, price: {order_pirce}"
                            )
                            logger.debug(
                                f"{position.contract.code} | {position.status}"
                            )
                else:
                    cancel_quantity = msg["status"].get("cancel_quantity", 0)
                    if msg["order"]["action"] == Action.Sell:
                        if position.cond.quantity < 0:
                            position.status.entry_order_quantity += cancel_quantity
                            logger.info(
                                f"{position.contract.code} | canceled short entry order with {cancel_quantity}"
                            )
                            logger.debug(
                                f"{position.contract.code} | {position.status}"
                            )
                        else:
                            position.status.cover_order_quantity += cancel_quantity
                            logger.info(
                                f"{position.contract.code} | canceled long cover order with {cancel_quantity}"
                            )
                            logger.debug(
                                f"{position.contract.code} | {position.status}"
                            )
                    else:
                        if position.cond.quantity < 0:
                            position.status.cover_order_quantity -= cancel_quantity
                            logger.info(
                                f"{position.contract.code} | canel short cover order with {cancel_quantity}"
                            )
                            logger.debug(
                                f"{position.contract.code} | {position.status}"
                            )
                        else:
                            position.status.entry_order_quantity -= cancel_quantity
                            logger.info(
                                f"{position.contract.code} | canel long entry order with {cancel_quantity}"
                            )
                            logger.debug(
                                f"{position.contract.code} | {position.status}"
                            )
                    position.status.cancel_quantity += cancel_quantity
        else:
            logger.error(f"Please Check: {msg}")

    def deal_handler(self, msg: Dict, position: Position):
        with position.lock:
            deal_quantity = msg["quantity"]
            deal_price = msg["price"]
            if msg["action"] == Action.Sell:
                position.status.open_quantity -= deal_quantity
                if position.cond.quantity < 0:
                    position.status.entry_quantity -= deal_quantity
                    logger.info(
                        f"{position.contract.code} | short entry order deal with {deal_quantity}, price: {deal_price}"
                    )
                    logger.debug(f"{position.contract.code} | {position.status}")
                else:
                    position.status.cover_quantity -= deal_quantity
                    logger.info(
                        f"{position.contract.code} | long cover order deal with {deal_quantity}, price: {deal_price}"
                    )
                    logger.debug(f"{position.contract.code} | {position.status}")
            else:
                position.status.open_quantity += deal_quantity
                if position.cond.quantity < 0:
                    position.status.cover_quantity += deal_quantity
                    logger.info(
                        f"{position.contract.code} | short cover order deal with {deal_quantity}, price: {deal_price}"
                    )
                    logger.debug(f"{position.contract.code} | {position.status}")
                else:
                    position.status.entry_quantity += deal_quantity
                    logger.info(
                        f"{position.contract.code} | long entry order deal with {deal_quantity}, price: {deal_price}"
                    )
                    logger.debug(f"{position.contract.code} | {position.status}")
