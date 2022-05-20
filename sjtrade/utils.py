import math


def price_ceil(price: float) -> float:
    logp = math.floor(math.log10(price))
    quinary = ((price / 10**logp) // 5) if logp >= 1 else 1
    n = min(10 ** (3 - logp - quinary), 100)
    return round(math.ceil(price * n + (5 - (price * n % 5)) * (1 - quinary)) / n, 2)


def price_floor(price: float) -> float:
    logp = math.floor(math.log10(price))
    quinary = ((price / 10**logp) // 5) if logp >= 1 else 1
    n = min(10 ** (3 - logp - quinary), 100)
    return round(math.floor(price * n - ((price * n % 5) * (1 - quinary))) / n, 2)


def price_round(price: float, up: bool = False):
    roudnf = math.ceil if up else math.floor
    logp = math.floor(math.log10(price))
    quinary = ((price / 10**logp) // 5) if logp >= 1 else 1
    n = min(10 ** (3 - logp - quinary), 100)
    return round(
        roudnf(price * n + ((5 * int(up) - (price * n % 5)) * (1 - quinary))) / n, 2
    )
