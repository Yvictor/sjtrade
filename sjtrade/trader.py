from typing import Dict
import shioaji as sj


class SJTrader:
    def __init__(self, api: sj.Shioaji):
        self.api = api

    def start(self):
        pass

    def place_entry_order(self, position: Dict[str, int], pct: float):
        return [self.api.Contracts.Stocks[code].reference * pct for code, pos in position.items()]
