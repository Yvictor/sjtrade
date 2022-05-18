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
