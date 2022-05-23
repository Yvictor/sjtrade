from typing import Dict, List
import shioaji as sj

from .utils import price_round
from loguru import logger
from shioaji.constant import Action, TFTStockPriceType, TFTOrderType, QuoteVersion


class SJTrader:
    def __init__(self, api: sj.Shioaji):
        self.api = api

    def start(self):
        pass

    def place_entry_order(
        self, position: Dict[str, int], pct: float
    ) -> List[sj.order.Trade]:
        for code in position:
            if not self.api.Contracts.Stocks[code]:
                logger.warning(f"Code: {code} not exist in TW Stock.")
            else:
                self.api.quote.subscribe(
                    self.api.Contracts.Stocks[code], version=QuoteVersion.v1
                )
        return [
            self.api.place_order(
                contract=self.api.Contracts.Stocks[code],
                order=sj.Order(
                    price=price_round(
                        self.api.Contracts.Stocks[code].reference * pct, pos > 0
                    ),
                    quantity=abs(pos),
                    action=Action.Buy if pos > 0 else Action.Sell,
                    price_type=TFTStockPriceType.LMT,
                    order_type=TFTOrderType.ROD,
                ),
            )
            for code, pos in position.items()
            if self.api.Contracts.Stocks[code]
        ]
