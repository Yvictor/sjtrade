from sjtrade.utils import price_ceil, price_floor


def test_price_ceil():
    assert price_ceil(0.111) == 0.12
    assert price_ceil(1.111) == 1.12
    assert price_ceil(9.999) == 10
    assert price_ceil(10.0377878) == 10.05
    assert price_ceil(50.14) == 50.2
    assert price_ceil(131.444) == 131.5
    assert price_ceil(998.1) == 999
    assert price_ceil(1053.1) == 1055
    assert price_ceil(9981.4) == 9990


def test_price_floor():
    assert price_floor(0.119) == 0.11
    assert price_floor(1.119) == 1.11
    assert price_floor(9.999) == 9.99
    assert price_floor(10.0877878) == 10.05
    assert price_floor(50.18) == 50.1
    assert price_floor(131.9894) == 131.5
    assert price_floor(998.8) == 998
    assert price_floor(1058.9) == 1055
    assert price_floor(9989.5) == 9980
