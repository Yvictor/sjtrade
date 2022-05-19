import math


def price_ceil(price: float) -> float:
    if price < 10:
        return math.ceil(price * 100) / 100.0
    elif price < 50:
        return math.ceil()
    elif price < 100:
        return math.ceil(price * 10) / 10.0

def price_floor(price: float) -> float:
    return 0
