import pytest
import time
import datetime
import loguru
from pytest_mock import MockFixture, MockerFixture
import shioaji as sj

from decimal import Decimal
from dataclasses import dataclass
from sjtrade.position import PriceSet
from sjtrade.trader import (
    Position,
    PositionCond,
    SJTrader,
    SimulationShioaji,
    StrategyBasic,
)
from shioaji.constant import (
    Action,
    TFTStockPriceType,
    TFTOrderType,
    QuoteVersion,
    Exchange,
    OrderState,
    TFTStockOrderLot,
    StockOrderCond,
    StockFirstSell,
)


@dataclass
class TickSTKv1:
    code: str
    datetime: datetime.datetime
    close: Decimal
    simtrade: bool


@pytest.fixture
def positions():
    return {"1605": -1, "6290": -3, "0000": 3}


@pytest.fixture
def sjtrader(api: sj.Shioaji, mocker: MockFixture, positions: dict) -> SJTrader:
    sjtrader = SJTrader(api)
    sjtrader.stratagy = StrategyBasic(entry_pct=0.05, contracts=api.Contracts)
    sjtrader.stratagy.read_position_func = mocker.MagicMock()
    sjtrader.stratagy.read_position_func.return_value = positions
    return sjtrader


@pytest.fixture
def sjtrader_sim(api: sj.Shioaji, mocker: MockFixture, positions: dict) -> SJTrader:
    sjtrader = SJTrader(api, simulation=True)
    sjtrader.stratagy = StrategyBasic(entry_pct=0.05, contracts=api.Contracts)
    sjtrader.stratagy.read_position_func = mocker.MagicMock()
    sjtrader.stratagy.read_position_func.return_value = positions
    return sjtrader


@pytest.fixture
def sjtrader_entryed(sjtrader: SJTrader):
    sjtrader.api.place_order.side_effect = lambda contract, order, timeout: (
        sj.order.Trade(
            contract,
            order,
            sj.order.OrderStatus(status=sj.order.Status.PreSubmitted),
        )
    )
    res = sjtrader.place_entry_positions()
    return sjtrader


@pytest.fixture
def sjtrader_entryed_sim(sjtrader_sim: SJTrader, positions: dict) -> SJTrader:
    res = sjtrader_sim.place_entry_positions()
    return sjtrader_sim


def test_sjtrader(api: sj.Shioaji):
    sjtrader = SJTrader(api)
    sjtrader.stratagy = StrategyBasic()
    assert hasattr(sjtrader, "api")
    sjtrader.stop_profit_pct = 0.1
    assert sjtrader.stop_profit_pct == 0.1
    assert sjtrader.stratagy.stop_profit_pct == 0.1
    sjtrader.stop_loss_pct = 0.1
    assert sjtrader.stop_loss_pct == 0.1
    assert sjtrader.stratagy.stop_loss_pct == 0.1
    sjtrader.position_filepath = "pos.txt"
    assert sjtrader.position_filepath == "pos.txt"
    assert sjtrader.stratagy.position_filepath == "pos.txt"
    sjtrader.entry_pct = 0.07
    assert sjtrader.entry_pct == 0.07
    assert sjtrader.stratagy.entry_pct == 0.07


def test_sjtrader_start(sjtrader: SJTrader, mocker: MockerFixture):
    sleep_until_mock = mocker.patch("sjtrade.trader.sleep_until")
    sjtrader.start()
    sjtrader.stratagy.read_position_func.assert_called_once()
    sjtrader.api.set_order_callback.assert_called_once_with(sjtrader.order_deal_handler)
    sjtrader.api.quote.set_on_tick_stk_v1_callback.assert_has_calls(
        [((sjtrader.cancel_preorder_handler,),), ((sjtrader.intraday_handler,),)]
    )
    sleep_until_mock.assert_has_calls(
        [
            mocker.call(datetime.time(8, 45)),
            mocker.call(datetime.time(8, 54, 59)),
            mocker.call(datetime.time(8, 59, 55)),
            mocker.call(datetime.time(13, 25, 59)),
        ]
    )


def test_sjtrader_sj_event_handler(sjtrader: SJTrader, logger: loguru._logger.Logger):
    sjtrader.sj_event_handel(0, 0, "info", "event")
    logger.info.assert_called_once()


def test_sjtrader_place_entry_order(
    sjtrader: SJTrader,
    logger: loguru._logger.Logger,
    logger_stratagy: loguru._logger.Logger,
):
    sjtrader.api.place_order.side_effect = (
        lambda contract, order, timeout: sj.order.Trade(
            contract, order, sj.order.OrderStatus(status=sj.order.Status.PreSubmitted)
        )
    )
    sjtrader.stop_loss_pct = 0.085
    sjtrader.stop_profit_pct = 0.09
    res = sjtrader.place_entry_positions()
    logger_stratagy.warning.assert_called_once()
    sjtrader.api.quote.subscribe.assert_has_calls(
        [
            ((sjtrader.api.Contracts.Stocks["1605"],), dict(version=QuoteVersion.v1)),
            ((sjtrader.api.Contracts.Stocks["6290"],), dict(version=QuoteVersion.v1)),
        ]
    )
    assert logger.info.call_count == 2
    sjtrader.api.update_status.assert_called_once()
    expected = [
        sj.order.Trade(
            sjtrader.api.Contracts.Stocks["1605"],
            sj.Order(
                price=41.35,
                quantity=1,
                action=Action.Sell,
                price_type=TFTStockPriceType.LMT,
                order_type=TFTOrderType.ROD,
                custom_field=sjtrader.name,
                first_sell=StockFirstSell.Yes,
            ),
            status=sj.order.OrderStatus(status=sj.order.Status.PreSubmitted),
        ),
        sj.order.Trade(
            sjtrader.api.Contracts.Stocks["6290"],
            sj.Order(
                price=60.1,
                quantity=3,
                action=Action.Sell,
                price_type=TFTStockPriceType.LMT,
                order_type=TFTOrderType.ROD,
                first_sell=StockFirstSell.Yes,
                custom_field=sjtrader.name,
            ),
            status=sj.order.OrderStatus(status=sj.order.Status.PreSubmitted),
        ),
    ]
    cond_1605 = PositionCond(
        quantity=-1,
        entry_price=[
            PriceSet(price=41.35, quantity=-1, price_type=TFTStockPriceType.LMT, in_transit_quantity=-1)
        ],
        stop_loss_price=[
            PriceSet(price=42.7, quantity=-1, price_type=TFTStockPriceType.MKT)
        ],
        stop_profit_price=[
            PriceSet(price=35.9, quantity=-1, price_type=TFTStockPriceType.MKT)
        ],
        cover_price=[],
    )
    cond_6290 = PositionCond(
        quantity=-3,
        entry_price=[
            PriceSet(price=60.1, quantity=-3, price_type=TFTStockPriceType.LMT, in_transit_quantity=-3)
        ],
        stop_loss_price=[
            PriceSet(price=62.1, quantity=-3, price_type=TFTStockPriceType.MKT)
        ],
        stop_profit_price=[
            PriceSet(price=52.2, quantity=-3, price_type=TFTStockPriceType.MKT)
        ],
        cover_price=[],
    )
    assert sjtrader.positions["1605"].cond == cond_1605
    assert sjtrader.positions["6290"].cond == cond_6290
    assert sjtrader.positions == {
        "1605": Position(
            contract=sjtrader.api.Contracts.Stocks["1605"],
            cond=cond_1605,
            entry_trades=[
                expected[0],
            ],
            lock=sjtrader.positions["1605"].lock
            # cover_trades=[],
        ),
        "6290": Position(
            contract=sjtrader.api.Contracts.Stocks["6290"],
            cond=cond_6290,
            entry_trades=[
                expected[1],
            ],
            lock=sjtrader.positions["6290"].lock
            # cover_trades=[],
        ),
    }
    assert len(res) == 2
    assert res == sjtrader.positions


def test_sjtrader_cancel_preorder_handler(
    sjtrader_entryed: SJTrader, mocker: MockerFixture, logger: loguru._logger.Logger
):
    tick = TickSTKv1("1605", "2022-05-25 08:45:01", Decimal("43.3"), True)

    def make_cancel_order_status(trade):
        trade.status.status = sj.order.Status.Cancelled
        trade.status.cancel_quantity = trade.order.quantity

    sjtrader_entryed.update_status = mocker.MagicMock(
        side_effect=make_cancel_order_status
    )

    sjtrader_entryed.cancel_preorder_handler(Exchange.TSE, tick)
    sjtrader_entryed.api.cancel_order.assert_called_once_with(
        sjtrader_entryed.positions["1605"].entry_trades[0], timeout=0
    )
    assert logger.info.called
    # TODO need single trade update status interface
    # sjtrader_entryed.update_status.assert_called_once_with(
    #     sjtrader_entryed.positions["1605"].entry_trades[0]
    # )
    # sjtrader.api._solace.update_status.assert_called()
    # assert sjtrader_entryed.positions["1605"].cancel_quantity == -1


def test_sjtrader_re_entry_order(
    sjtrader_entryed: SJTrader, mocker: MockerFixture, logger: loguru._logger.Logger
):
    tick = TickSTKv1("1605", "2022-05-25 08:45:01", Decimal("43.3"), True)

    def make_cancel_order_status(trade, timeout):
        trade.status.status = sj.order.Status.Cancelled
        trade.status.cancel_quantity = trade.order.quantity

    sjtrader_entryed.update_status = mocker.MagicMock(
        side_effect=make_cancel_order_status
    )
    position = sjtrader_entryed.positions["1605"]
    sjtrader_entryed.cancel_preorder_handler(position, tick)

    tick = TickSTKv1("1605", "2022-05-25 09:00:01", Decimal("35"), False)
    sjtrader_entryed.re_entry_order(position, tick)
    sjtrader_entryed.api.place_order.assert_called_with(
        contract=position.contract,
        order=sj.order.TFTStockOrder(
            price=0,
            quantity=1,
            action=Action.Sell,
            price_type=TFTStockPriceType.MKT,
            order_type=TFTOrderType.ROD,
            first_sell=StockFirstSell.Yes,
            custom_field="dt1",
        ),
        timeout=0,
    )
    assert logger.info.called


def test_sjtrader_stop_profit(
    sjtrader_entryed: SJTrader, mocker: MockerFixture, logger: loguru._logger.Logger
):
    tick = TickSTKv1("1605", "2022-05-25 08:45:01", Decimal("35.5"), False)
    position = sjtrader_entryed.positions["1605"]
    position.status.open_quantity = -1
    sjtrader_entryed.place_cover_order = mocker.MagicMock()
    sjtrader_entryed.stop_profit(position, tick)
    sjtrader_entryed.place_cover_order.assert_called_once()
    assert logger.info.called


def test_sjtrader_stop_loss(
    sjtrader_entryed: SJTrader, mocker: MockerFixture, logger: loguru._logger.Logger
):
    tick = TickSTKv1("1605", "2022-05-25 08:45:01", Decimal("43.3"), False)
    position = sjtrader_entryed.positions["1605"]
    position.status.open_quantity = -1
    sjtrader_entryed.place_cover_order = mocker.MagicMock()
    sjtrader_entryed.stop_loss(position, tick)
    sjtrader_entryed.place_cover_order.assert_called_once()
    assert logger.info.called


def test_sjtrader_intraday_handler(sjtrader_entryed: SJTrader, mocker: MockerFixture):
    tick = TickSTKv1("1605", "2022-05-25 08:45:01", Decimal("43.3"), True)
    sjtrader_entryed.re_entry_order = mocker.MagicMock()
    sjtrader_entryed.stop_profit = mocker.MagicMock()
    sjtrader_entryed.stop_loss = mocker.MagicMock()
    sjtrader_entryed.intraday_handler(Exchange.TSE, tick)
    sjtrader_entryed.re_entry_order.assert_called_once()
    sjtrader_entryed.stop_profit.assert_called_once()
    sjtrader_entryed.stop_loss.assert_called_once()


def test_sjtrader_place_cover_order(
    sjtrader_entryed: SJTrader, logger: loguru._logger.Logger
):
    position = sjtrader_entryed.positions["1605"]
    position.status.open_quantity = -1
    sjtrader_entryed.place_cover_order(position)
    order_msg = gen_sample_order_msg("1605", Action.Buy, 1, op_type="New", op_code="00")
    sjtrader_entryed.order_handler(order_msg, position)
    assert position.status.cover_order_quantity == 1
    position.cover_trades[0].order.price == 43.3
    # TODO assert called once with
    # sjtrader_entryed.api.place_order.assert_has_calls([
    #     ((), dict(contract=position.contract, order=sj.order.TFTStockOrder(
    #         price=0,
    #         quantity=
    #     )))
    # ])
    assert len(position.cover_trades) == 1
    assert logger.info.called


def test_sjtrader_open_position_cover(
    sjtrader_entryed: SJTrader, logger: loguru._logger.Logger
):
    position = sjtrader_entryed.positions["1605"]
    position.open_quantity = -1
    sjtrader_entryed.place_cover_order(position)
    order_msg = gen_sample_order_msg("1605", Action.Buy, 1, op_type="New", op_code="00")
    sjtrader_entryed.order_handler(order_msg, position)
    sjtrader_entryed.open_position_cover()
    assert logger.info.called


@pytest.fixture
def order_msg():
    return {
        "operation": {"op_type": "New", "op_code": "00", "op_msg": ""},
        "order": {
            "id": "c21b876d",
            "seqno": "429832",
            "ordno": "W2892",
            "action": "Sell",
            "price": 44.3,
            "quantity": 1,
            "order_cond": "Cash",
            "order_lot": "Common",
            "custom_field": "dt1",
            "order_type": "ROD",
            "price_type": "LMT",
        },
        "status": {
            "id": "c21b876d",
            "exchange_ts": 1583828972,
            "modified_price": 0,
            "cancel_quantity": 0,
            "web_id": "137",
        },
        "contract": {
            "security_type": "STK",
            "exchange": "TSE",
            "code": "1605",
            "symbol": "",
            "name": "",
            "currency": "TWD",
        },
    }


@pytest.fixture
def deal_msg():
    return {
        "trade_id": "12ab3456",
        "exchange_seq": "123456",
        "broker_id": "your_broker_id",
        "account_id": "your_account_id",
        "action": Action.Buy,
        "code": "1605",
        "order_cond": StockOrderCond.Cash,
        "order_lot": TFTStockOrderLot.Common,
        "price": 12,
        "quantity": 10,
        "web_id": "137",
        "custom_field": "dt1",
        "ts": 1583828972,
    }


def gen_sample_order_msg(
    code: str, action: Action, quantity: int, op_type: str, op_code: str
):
    return {
        "operation": {"op_type": op_type, "op_code": op_code, "op_msg": ""},
        "order": {
            "id": "c21b876d",
            "seqno": "429832",
            "ordno": "W2892",
            "action": action,
            "price": 44.3,
            "quantity": quantity,
            "order_cond": "Cash",
            "order_lot": "Common",
            "custom_field": "dt1",
            "order_type": "ROD",
            "price_type": "LMT",
        },
        "status": {
            "id": "c21b876d",
            "exchange_ts": 1583828972,
            "order_quantity": quantity if op_type == "New" else 0,
            "modified_price": 0.0,
            "cancel_quantity": quantity if op_type == "Cancel" else 0,
            "web_id": "137",
        },
        "contract": {
            "security_type": "STK",
            "exchange": "TSE",
            "code": code,
            "symbol": "",
            "name": "",
            "currency": "TWD",
        },
    }


def gen_sample_deal_msg(code: str, action: Action, quantity: int):
    return {
        "trade_id": "12ab3456",
        "exchange_seq": "123456",
        "broker_id": "your_broker_id",
        "account_id": "your_account_id",
        "action": action,
        "code": code,
        "order_cond": StockOrderCond.Cash,
        "order_lot": TFTStockOrderLot.Common,
        "price": 12,
        "quantity": quantity,
        "web_id": "137",
        "custom_field": "dt1",
        "ts": 1583828972,
    }


def test_sjtrader_order_deal_handler_receive_order_msg(
    sjtrader_entryed: SJTrader, order_msg: dict, mocker: MockerFixture
):
    sjtrader_entryed.order_handler = mocker.MagicMock()
    sjtrader_entryed.order_deal_handler(OrderState.TFTOrder, order_msg)
    sjtrader_entryed.order_handler.assert_called_once_with(
        order_msg,
        sjtrader_entryed.positions["1605"],
    )


def test_sjtrader_order_deal_handler_receive_deal_msg(
    sjtrader_entryed: SJTrader, deal_msg: dict, mocker: MockerFixture
):
    sjtrader_entryed.deal_handler = mocker.MagicMock()
    sjtrader_entryed.order_deal_handler(OrderState.TFTDeal, deal_msg)
    sjtrader_entryed.deal_handler.assert_called_once_with(
        deal_msg,
        sjtrader_entryed.positions["1605"],
    )


def test_sjtrader_order_handler(
    sjtrader_entryed: SJTrader, logger: loguru._logger.Logger
):
    position = sjtrader_entryed.positions["1605"]
    order_msg = gen_sample_order_msg(
        "1605", Action.Sell, 1, op_type="New", op_code="00"
    )
    sjtrader_entryed.order_handler(order_msg, position)
    assert position.status.entry_order_quantity == -1

    order_msg = gen_sample_order_msg(
        "1605", Action.Sell, 1, op_type="Cancel", op_code="00"
    )
    sjtrader_entryed.order_handler(order_msg, position)
    assert position.status.entry_order_quantity == 0

    order_msg = gen_sample_order_msg("1605", Action.Buy, 1, op_type="New", op_code="00")
    sjtrader_entryed.order_handler(order_msg, position)
    assert position.status.cover_order_quantity == 1

    order_msg = gen_sample_order_msg(
        "1605", Action.Buy, 1, op_type="Cancel", op_code="00"
    )
    sjtrader_entryed.order_handler(order_msg, position)
    assert position.status.cover_order_quantity == 0
    assert logger.info.called


def test_sjtrader_deal_handler(
    sjtrader_entryed: SJTrader, logger: loguru._logger.Logger
):
    position = sjtrader_entryed.positions["1605"]
    deal_msg = gen_sample_deal_msg("1605", Action.Sell, 1)
    sjtrader_entryed.deal_handler(deal_msg, position)
    assert position.status.open_quantity == -1
    assert position.status.entry_quantity == -1
    deal_msg = gen_sample_deal_msg("1605", Action.Buy, 1)
    sjtrader_entryed.deal_handler(deal_msg, position)
    assert position.status.open_quantity == 0
    assert position.status.cover_quantity == 1
    assert logger.info.called


def test_sim_sj_quote_callback(api: sj.Shioaji):
    sim_api = SimulationShioaji(print)
    contract = api.Contracts.Stocks["1605"]
    order = sj.Order(
        price=35,
        quantity=1,
        action=Action.Sell,
        price_type=TFTStockPriceType.LMT,
        order_type=TFTOrderType.ROD,
        custom_field="dt1",
    )
    sim_api.place_order(
        contract,
        order,
    )
    order = sj.Order(
        price=34,
        quantity=1,
        action=Action.Sell,
        price_type=TFTStockPriceType.LMT,
        order_type=TFTOrderType.ROD,
        custom_field="dt1",
    )
    sim_api.place_order(
        contract,
        order,
    )
    time.sleep(1.1)
    tick = TickSTKv1("1605", "2022-05-25 09:00:01", 34.5, False)
    assert len(sim_api.lmt_price_trades["1605"]) == 2
    sim_api.quote_callback(Exchange.TSE, tick)
    assert sim_api.snapshots["1605"].price == 34.5
    assert len(sim_api.lmt_price_trades["1605"]) == 1
    tick = TickSTKv1("1605", "2022-05-25 09:00:02", 36, False)
    sim_api.quote_callback(Exchange.TSE, tick)
    assert sim_api.snapshots["1605"].price == 36
    assert "1605" not in sim_api.lmt_price_trades


def test_sim_sj_place_order(api: sj.Shioaji):
    sim_api = SimulationShioaji(print)
    contract = api.Contracts.Stocks["1605"]
    order = sj.Order(
        price=41.35,
        quantity=1,
        action=Action.Sell,
        price_type=TFTStockPriceType.MKT,
        order_type=TFTOrderType.ROD,
        custom_field="dt1",
    )
    trade = sim_api.place_order(
        contract,
        order,
    )
    time.sleep(0.55)
    assert trade.contract == contract
    # assert trade.order == order
    assert trade.order.seqno == "000001"
    assert trade.order.id == "c2c49415"
    assert trade.order.ordno != ""
    assert trade.status.status == "Submitted"
    time.sleep(0.1)
    assert trade.status.deal_quantity == 1


def test_sim_sj_cancel_order(api: sj.Shioaji):
    sim_api = SimulationShioaji(print)
    contract = api.Contracts.Stocks["1605"]
    order = sj.Order(
        price=41.35,
        quantity=1,
        action=Action.Sell,
        price_type=TFTStockPriceType.LMT,
        order_type=TFTOrderType.ROD,
        custom_field="dt1",
    )
    trade = sim_api.place_order(
        contract,
        order,
    )
    time.sleep(0.55)
    trade = sim_api.cancel_order(trade)
    time.sleep(0.55)
    assert trade.status.status == sj.order.Status.Cancelled

    order = sj.Order(
        price=41.35,
        quantity=1,
        action=Action.Sell,
        price_type=TFTStockPriceType.MKT,
        order_type=TFTOrderType.ROD,
        custom_field="dt1",
    )
    trade = sim_api.place_order(
        contract,
        order,
    )
    time.sleep(0.55)
    trade = sim_api.cancel_order(trade)
    time.sleep(0.55)
    assert trade.status.status == sj.order.Status.Filled


def test_sim_sj_update_status(api: sj.Shioaji):
    sim_api = SimulationShioaji(print)
    sim_api.update_status()


def test_sjtrader_sim(api: sj.Shioaji):
    sjtrader = SJTrader(api, simulation=True)
    assert hasattr(sjtrader, "simulation_api")


def test_sjtrader_sim_place_entry_order(
    sjtrader_sim: SJTrader,
    logger: loguru._logger.Logger,
    logger_stratagy: loguru._logger.Logger,
):
    res = sjtrader_sim.place_entry_positions()
    logger_stratagy.warning.assert_called_once()
    sjtrader_sim.api.quote.subscribe.assert_has_calls(
        [
            (
                (sjtrader_sim.api.Contracts.Stocks["1605"],),
                dict(version=QuoteVersion.v1),
            ),
            (
                (sjtrader_sim.api.Contracts.Stocks["6290"],),
                dict(version=QuoteVersion.v1),
            ),
        ]
    )
    assert logger.info.call_count == 2
    assert len(res) == 2


def test_sjtrader_sim_cancel_preorder_handler(
    sjtrader_entryed_sim: SJTrader, logger: loguru._logger.Logger
):
    tick = TickSTKv1("1605", "2022-05-25 08:45:01", 43.3, True)
    sjtrader_entryed_sim.cancel_preorder_handler(Exchange.TSE, tick)

    assert logger.info.called
    time.sleep(0.55)
    assert sjtrader_entryed_sim.positions["1605"].status.cancel_quantity == 1


def test_sjtrader_sim_re_entry_order(
    sjtrader_entryed_sim: SJTrader, logger: loguru._logger.Logger
):
    tick = TickSTKv1("1605", "2022-05-25 08:45:01", 43.3, True)
    position = sjtrader_entryed_sim.positions["1605"]
    sjtrader_entryed_sim.cancel_preorder_handler(position, tick)
    time.sleep(0.55)
    assert sjtrader_entryed_sim.positions["1605"].status.cancel_preorder == True
    tick = TickSTKv1("1605", "2022-05-25 09:00:01", 35, False)
    sjtrader_entryed_sim.re_entry_order(position, tick)
    assert logger.info.called
    time.sleep(0.65)
    assert sjtrader_entryed_sim.positions["1605"].status.entry_order_quantity == -1
