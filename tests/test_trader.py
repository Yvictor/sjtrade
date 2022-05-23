import pytest
import loguru
import shioaji as sj

from sjtrade.trader import SJTrader
from pytest_mock import MockerFixture
from shioaji.constant import Action, TFTStockPriceType, TFTOrderType, QuoteVersion


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
    res = sjtrader.place_entry_order(position, 1.05)
    logger.warning.assert_called_once()
    sjtrader.api.quote.subscribe.assert_has_calls(
        [
            ((sjtrader.api.Contracts.Stocks["1605"],), dict(version=QuoteVersion.v1)),
            ((sjtrader.api.Contracts.Stocks["6290"],), dict(version=QuoteVersion.v1)),
        ]
    )
    assert len(res) == 2
    assert res == [
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
