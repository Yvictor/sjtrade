from turtle import position
import pytest
import shioaji as sj

from sjtrade.trader import SJTrader


@pytest.fixture
def sjtrader(api: sj.Shioaji) -> SJTrader:
    return SJTrader(api)


def test_sjtrader(api: sj.Shioaji):
    sjtrader = SJTrader(api)
    assert hasattr(sjtrader, "api")


def test_sjtrader_start(sjtrader: SJTrader):
    sjtrader.start()


def test_sjtrader_place_entry_order(sjtrader: SJTrader):
    position = {"1605": -1, "6290": -3}
    res = sjtrader.place_entry_order(position, 1.05)
    assert len(res) == len(position)
    assert res == [41.37, 60.165]
