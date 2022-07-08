from dataclasses import dataclass


@dataclass
class Snapshot:
    price: float
    bid: float = 0
    ask: float = 0
