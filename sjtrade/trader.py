import datetime
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Union
from threading import Lock
from concurrent.futures import Future, ThreadPoolExecutor
import shioaji as sj

from .utils import quantity_split, sleep_until
from .simulation_shioaji import SimulationShioaji
from .stratage import StratageBasic
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
class PositionCond:
    quantity: int
    entry_price: Dict[float, int]
    stop_loss_price: Dict[float, int]
    stop_profit_price: Dict[float, int]


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
        self.executor = ThreadPoolExecutor()
        self.simulation = simulation
        if simulation:
            self.simulation_api = SimulationShioaji(self.order_deal_handler)
        self.api.set_order_callback(self.order_deal_handler)
        self.api.quote.set_event_callback(self.sj_event_handel)
        self.stratage = StratageBasic(contracts=self.api.Contracts)
        # self.account = api.stock_account
        # self.entry_trades: Dict[str, sj.order.Trade] = {}

    def start(
        self,
        entry_time: datetime.time = datetime.time(8, 45),
        cancel_preorder_time: datetime.time = datetime.time(8, 54, 59),
        intraday_handler_time: datetime.time = datetime.time(8, 59, 55),
        cover_time: datetime.time = datetime.time(13, 25, 59),
    ):
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
        self.stratage.stop_loss_pct = self._stop_loss_pct

    @property
    def stop_profit_pct(self) -> float:
        return self._stop_profit_pct

    @stop_profit_pct.setter
    def stop_profit_pct(self, v: float) -> float:
        self._stop_profit_pct = v
        self.stratage.stop_profit_pct = self._stop_profit_pct

    @property
    def entry_pct(self) -> float:
        return self._entry_pct

    @entry_pct.setter
    def entry_pct(self, v: float) -> float:
        self._entry_pct = v
        self.stratage.entry_pct = self._entry_pct

    @property
    def position_filepath(self) -> float:
        return self._position_filepath

    @position_filepath.setter
    def position_filepath(self, v: str) -> float:
        self._position_filepath = v
        self.stratage.position_filepath = self._position_filepath

    def sj_event_handel(self, resp_code: int, event_code: int, info: str, event: str):
        logger.info(
            f"Response Code: {resp_code} | Event Code: {event_code} | Info: {info} | Event: {event}"
        )

    def place_entry_order(
        self,
        code: str,
        pos: int,
        entry_price: Dict[float, int],
        stop_profit_price: Dict[float, int],
        stop_loss_price: Dict[float, int],
    ):
        api = self.simulation_api if self.simulation else self.api
        contract = self.api.Contracts.Stocks[code]
        if not contract:
            logger.warning(f"Code: {code} not exist in TW Stock.")
        else:
            self.positions[code] = Position(
                contract=contract,
                cond=PositionCond(
                    quantity=pos,
                    entry_price=entry_price,
                    stop_loss_price=stop_loss_price,
                    stop_profit_price=stop_profit_price,
                ),
            )
            self.api.quote.subscribe(contract, version=QuoteVersion.v1)
            for price, price_quantity in self.positions[code].cond.entry_price.items():
                quantity_s = quantity_split(price_quantity, threshold=499)
                with self.positions[code].lock:
                    for q in quantity_s:
                        trade = api.place_order(
                            contract=contract,
                            order=sj.Order(
                                price=price,
                                quantity=abs(q),
                                action=Action.Buy if pos > 0 else Action.Sell,
                                price_type=TFTStockPriceType.LMT,
                                order_type=TFTOrderType.ROD,
                                first_sell=StockFirstSell.No
                                if pos > 0
                                else StockFirstSell.Yes,
                                custom_field=self.name,
                            ),
                            timeout=0,
                        )
                        self.positions[code].entry_trades.append(trade)
                        logger.info(f"{code} | {trade.order}")

    def place_entry_positions(self) -> Dict[str, Position]:
        api = self.simulation_api if self.simulation else self.api
        for entry_kwarg in self.stratage.entry_positions():
            self.place_entry_order(**entry_kwarg)
        api.update_status()
        return self.positions

    def cancel_preorder_handler(self, exchange: Exchange, tick: sj.TickSTKv1):
        position = self.positions[tick.code]
        if self.simulation:
            api = self.simulation_api
        else:
            api = self.api
        # 8:55 - 8:59:55
        if tick.simtrade:
            if position.cond.quantity < 0 and tick.close == position.contract.limit_up:
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
                if position.status.cancel_preorder and tick.close < min(
                    position.cond.stop_loss_price.keys()
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
        # 9:00 -> 13:24:49 stop loss stop profit
        self.stop_loss(position, tick)
        self.stop_profit(position, tick)

    def stop_profit(self, position: Position, tick: sj.TickSTKv1):
        if not tick.simtrade:
            if position.status.open_quantity > 0 and tick.close >= min(
                position.cond.stop_profit_price.keys()
            ):
                self.place_cover_order(position)
                logger.info(
                    f"{position.contract.code} | price: {tick.close} cross over {position.cond.stop_profit_price}"
                )

            if position.status.open_quantity < 0 and tick.close <= max(
                position.cond.stop_profit_price.keys()
            ):
                self.place_cover_order(position)
                logger.info(
                    f"{position.contract.code} | price: {tick.close} cross under {position.cond.stop_profit_price}"
                )

    def stop_loss(self, position: Position, tick: sj.TickSTKv1):
        if not tick.simtrade:
            if position.status.open_quantity > 0 and tick.close <= max(
                position.cond.stop_loss_price.keys()
            ):
                self.place_cover_order(position)
                logger.info(
                    f"{position.contract.code} | price: {tick.close} cross under {position.cond.stop_loss_price}"
                )

            if position.status.open_quantity < 0 and tick.close >= min(
                position.cond.stop_loss_price.keys()
            ):
                self.place_cover_order(position)
                logger.info(
                    f"{position.contract.code} | price: {tick.close} cross over {position.cond.stop_loss_price}"
                )

    def place_cover_order(
        self, position: Position, with_price: bool = False
    ):  # TODO with price quantity
        if self.simulation:
            api = self.simulation_api
        else:
            api = self.api
        cover_quantity = (
            position.status.open_quantity + position.status.cover_order_quantity
        )
        if cover_quantity:
            action = Action.Buy if cover_quantity < 0 else Action.Sell
            # TODO support price with quantity for price, price_quantity in position.cond
            quantity_s = quantity_split(cover_quantity, threshold=499)
            for q in quantity_s:
                trade = api.place_order(
                    contract=position.contract,
                    order=sj.order.TFTStockOrder(
                        price=(
                            position.contract.limit_up
                            if action == Action.Buy
                            else position.contract.limit_down
                        )
                        if with_price
                        else 0,
                        quantity=abs(q),
                        action=action,
                        price_type=TFTStockPriceType.LMT
                        if with_price
                        else TFTStockPriceType.MKT,
                        order_type=TFTOrderType.ROD,
                        custom_field=self.name,
                    ),
                    timeout=0,
                )
                logger.info(f"{trade.contract.code} | {trade.order}")
                position.cover_trades.append(trade)
                api.update_status(trade=trade)

    def open_position_cover(self):
        if self.simulation:
            api = self.simulation_api
        else:
            api = self.api
        api.update_status()
        logger.info("start place cover order.")
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
            if position.status.open_quantity:
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
                        if position.cond.quantity < 0:
                            position.status.entry_order_quantity -= order_quantity
                            logger.info(
                                f"{position.contract.code} | place short entry order with {order_quantity}"
                            )
                        else:
                            position.status.cover_order_quantity -= order_quantity
                            logger.info(
                                f"{position.contract.code} | place long cover order with {order_quantity}"
                            )
                    else:
                        if position.cond.quantity < 0:
                            position.status.cover_order_quantity += order_quantity
                            logger.info(
                                f"{position.contract.code} | place short cover order with {order_quantity}"
                            )
                        else:
                            position.status.entry_order_quantity += order_quantity
                            logger.info(
                                f"{position.contract.code} | place long entry order with {order_quantity}"
                            )
                else:
                    cancel_quantity = msg["status"].get("cancel_quantity", 0)
                    if msg["order"]["action"] == Action.Sell:
                        if position.cond.quantity < 0:
                            position.status.entry_order_quantity += cancel_quantity
                            logger.info(
                                f"{position.contract.code} | canceled short entry order with {cancel_quantity}"
                            )
                        else:
                            position.status.cover_order_quantity += cancel_quantity
                            logger.info(
                                f"{position.contract.code} | canceled long cover order with {cancel_quantity}"
                            )
                    else:
                        if position.cond.quantity < 0:
                            position.status.cover_order_quantity -= cancel_quantity
                            logger.info(
                                f"{position.contract.code} | canel short cover order with {cancel_quantity}"
                            )
                        else:
                            position.status.entry_order_quantity -= cancel_quantity
                            logger.info(
                                f"{position.contract.code} | canel long entry order with {cancel_quantity}"
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
                else:
                    position.status.cover_quantity -= deal_quantity
                    logger.info(
                        f"{position.contract.code} | long cover order deal with {deal_quantity}, price: {deal_price}"
                    )
            else:
                position.status.open_quantity += deal_quantity
                if position.cond.quantity < 0:
                    position.status.cover_quantity += deal_quantity
                    logger.info(
                        f"{position.contract.code} | short cover order deal with {deal_quantity}, price: {deal_price}"
                    )
                else:
                    position.status.entry_quantity += deal_quantity
                    logger.info(
                        f"{position.contract.code} | long entry order deal with {deal_quantity}, price: {deal_price}"
                    )
