import pytest

from sjtrade.stratage import StratageBase


def test_stratage_base():
    stratage = StratageBase()
    with pytest.raises(NotImplementedError):
        stratage.entry_positions()

    with pytest.raises(NotImplementedError):
        stratage.cover_price_set(None)

    with pytest.raises(NotImplementedError):
        stratage.cover_positions(None)


    