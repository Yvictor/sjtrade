from dataclasses import dataclass
from decimal import Decimal

@dataclass
class Snapshot:
    price: Decimal
    bid: Decimal = 0
    ask: Decimal = 0
