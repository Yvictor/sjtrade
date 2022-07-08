import pytest

from sjtrade.strategy import StrategyBase


def test_stratage_base():
    stratage = StrategyBase()
    with pytest.raises(NotImplementedError):
        stratage.entry_positions()

    with pytest.raises(NotImplementedError):
        stratage.cover_price_set(None)

    with pytest.raises(NotImplementedError):
        stratage.cover_positions(None)


    