from sjtrade.utils import price_ceil, price_floor


def test_price_ceil():
    assert price_ceil(0.111) == 0.12
    assert price_ceil(9.999) == 10
    #assert price_ceil(10.02) == 10.05
    assert price_ceil(50.14) == 50.2


def test_price_floor():
    price_floor(0)
