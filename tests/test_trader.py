import pytest
import datetime
import loguru
from pytest_mock import MockerFixture
import shioaji as sj

from decimal import Decimal
from dataclasses import dataclass
from sjtrade.trader import SJTrader
from shioaji.constant import (
    Action,
    TFTStockPriceType,
    TFTOrderType,
    QuoteVersion,
    Exchange,
)


@dataclass
class TickSTKv1:
    code: str
    datetime: datetime.datetime
    close: Decimal
    simtrade: bool


@pytest.fixture
def sjtrader(api: sj.Shioaji) -> SJTrader:
    return SJTrader(api)


def test_sjtrader(api: sj.Shioaji):
    sjtrader = SJTrader(api)
    assert hasattr(sjtrader, "api")


def test_sjtrader_start(sjtrader: SJTrader):
    sjtrader.start()


def test_sjtrader_place_entry_order(sjtrader: SJTrader, logger: loguru._logger.Logger):
    sjtrader.api.place_order.side_effect = lambda contract, order: sj.order.Trade(
        contract, order, sj.order.OrderStatus(status=sj.order.Status.PreSubmitted)
    )
    position = {"1605": -1, "6290": -3, "0000": 3}
    sjtrader.stop_loss_pct = 0.085
    sjtrader.stop_profit_pct = 0.09
    res = sjtrader.place_entry_order(position, 1.05)
    logger.warning.assert_called_once()
    sjtrader.api.quote.subscribe.assert_has_calls(
        [
            ((sjtrader.api.Contracts.Stocks["1605"],), dict(version=QuoteVersion.v1)),
            ((sjtrader.api.Contracts.Stocks["6290"],), dict(version=QuoteVersion.v1)),
        ]
    )
    expected = [
        sj.order.Trade(
            sjtrader.api.Contracts.Stocks["1605"],
            sj.Order(
                price=41.35,
                quantity=1,
                action=Action.Sell,
                price_type=TFTStockPriceType.LMT,
                order_type=TFTOrderType.ROD,
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
            ),
            status=sj.order.OrderStatus(status=sj.order.Status.PreSubmitted),
        ),
    ]
    assert sjtrader.positions == {
        "1605": dict(
            contract=sjtrader.api.Contracts.Stocks["1605"],
            quantity=-1,
            stop_loss_price=42.7,
            stop_profit_price=35.9,
            cancel_quantity=0,
            entry_quantity=0,
            cover_quantity=0,
            entry_trades=[
                expected[0],
            ],
        ),
        "6290": dict(
            contract=sjtrader.api.Contracts.Stocks["6290"],
            quantity=-3,
            stop_loss_price=62.1,
            stop_profit_price=52.2,
            cancel_quantity=0,
            entry_quantity=0,
            cover_quantity=0,
            entry_trades=[
                expected[1],
            ],
        ),
    }
    assert len(res) == 2
    assert res == expected


def test_sjtrader_cancel_preorder_handler(sjtrader: SJTrader, mocker: MockerFixture):
    # tick = sj.TickSTKv1.from_content("1605", "2022-05-25", 39.5, 39, 39.4,)
    position = {"1605": -1, "6290": -3, "0000": 3}
    tick = TickSTKv1("1605", "2022-05-25 08:45:01", 43.3, True)
    sjtrader.api.place_order.side_effect = lambda contract, order: sj.order.Trade(
        contract, order, sj.order.OrderStatus(status=sj.order.Status.PreSubmitted)
    )

    def make_cancel_order_status(trade):
        trade.status.status = sj.order.Status.Cancelled
        trade.status.cancel_quantity = trade.order.quantity

    sjtrader.update_status = mocker.MagicMock(side_effect=make_cancel_order_status)

    sjtrader.place_entry_order(position, 1.05)
    sjtrader.cancel_preorder_handler(Exchange.TSE, tick)
    sjtrader.api.cancel_order.assert_called_once_with(
        sjtrader.positions["1605"]["entry_trades"][0]
    )
    # TODO need single trade update status interface
    sjtrader.update_status.assert_called_once_with(
        sjtrader.positions["1605"]["entry_trades"][0]
    )
    # sjtrader.api._solace.update_status.assert_called()
    assert sjtrader.positions["1605"]["cancel_quantity"] == -1


def test_sjtrader_re_entry_order(sjtrader: SJTrader):
    tick = TickSTKv1("1605", "2022-05-25 08:45:01", 43.3, True)
    sjtrader.re_entry_order(Exchange.TSE, tick)


def test_sjtrader_intraday_handler(sjtrader: SJTrader):
    tick = TickSTKv1("1605", "2022-05-25 08:45:01", 43.3, True)
    sjtrader.intraday_handler(Exchange.TSE, tick)


def test_sjtrader_place_cover_order(sjtrader: SJTrader):
    sjtrader.place_cover_order({})


def test_sjtrader_open_position_cover(sjtrader: SJTrader):
    sjtrader.open_position_cover()
