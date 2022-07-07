import shioaji as sj
from typing import Dict
from loguru import logger
from .io.file import read_position
from .utils import price_round
from .position import Position, PriceSet
from shioaji.constant import TFTStockPriceType


class StratageBase:
    name: str

    def entry_positions(self):
        raise NotImplementedError()

    def cover_price_set(self, position: Position):
        raise NotImplementedError()

    def cover_positions(self, positions: Dict[str, Position]):
        raise NotImplementedError()


class StratageBasic(StratageBase):
    def __init__(
        self,
        entry_pct: float = 0.05,
        stop_loss_pct: float = 0.09,
        stop_profit_pct: float = 0.09,
        position_filepath: str = "position.txt",
        contracts: sj.contracts.Contracts = sj.contracts.Contracts(),
    ) -> None:
        self.position_filepath = position_filepath
        self.entry_pct = entry_pct
        self.stop_loss_pct = stop_loss_pct
        self.stop_profit_pct = stop_profit_pct
        self.contracts = contracts
        self.name = "dt1"
        self.read_position_func = read_position

    def entry_positions(self):
        positions = self.read_position_func(self.position_filepath)
        entry_args = []
        for code, pos in positions.items():
            contract = self.contracts.Stocks[code]
            if not contract:
                logger.warning(f"Code: {code} not exist in TW Stock.")
                continue
            stop_loss_price = contract.reference * (
                1 + (-1 if pos > 0 else 1) * (self.stop_loss_pct)
            )
            stop_profit_price = contract.reference * (
                1 + (1 if pos > 0 else -1) * (self.stop_profit_pct)
            )
            entry_price = contract.reference * (
                1 + (-1 if pos > 0 else 1) * self.entry_pct
            )
            entry_args.append(
                {
                    "code": code,
                    "pos": pos,
                    "entry_price": [
                        PriceSet(
                            price=price_round(entry_price, pos > 0),
                            quantity=pos,
                            price_type=TFTStockPriceType.LMT,
                        )
                    ],
                    "stop_profit_price": [
                        PriceSet(
                            price=price_round(stop_profit_price, pos < 0),
                            quantity=pos,
                            price_type=TFTStockPriceType.MKT,
                        )
                    ],
                    "stop_loss_price": [
                        PriceSet(
                            price=price_round(stop_loss_price, pos > 0),
                            quantity=pos,
                            price_type=TFTStockPriceType.MKT,
                        )
                    ],
                }
            )
        return entry_args

    def cover_price_set(self, position: Position):
        return [
            PriceSet(
                price=43.3,
                quantity=position.cond.quantity * -1,
                price_type=TFTStockPriceType.LMT,
            )
        ]

    def cover_positions(self, positions: Dict[str, Position]):
        for code, position in positions.items():
            if not position.cond.cover_price:
                position.cond.cover_price = self.cover_price_set(position)
        return positions


class StratageAdvance(StratageBase):
    def __init__(
        self,
        entry_pct: float = -0.1,
        stop_loss_pct: float = 0.09,
        stop_profit_pct: float = 0.09,
        position_filepath: str = "position.txt",
        contracts: sj.contracts.Contracts = sj.contracts.Contracts(),
    ) -> None:
        self.position_filepath = position_filepath
        self.entry_pct = entry_pct
        self.stop_loss_pct = stop_loss_pct
        self.stop_profit_pct = stop_profit_pct
        self.contracts = contracts
        self.name = "dt1"
        self.read_position_func = read_position

    def entry_positions(self):
        positions = self.read_position_func(self.position_filepath)
        entry_args = []
        for code, pos in positions.items():
            contract = self.contracts.Stocks[code]
            if not contract:
                logger.warning(f"Code: {code} not exist in TW Stock.")
                continue
            stop_loss_price = contract.reference * (
                1 + (-1 if pos > 0 else 1) * (self.stop_loss_pct)
            )
            stop_profit_price = contract.reference * (
                1 + (1 if pos > 0 else -1) * (self.stop_profit_pct)
            )
            entry_price = contract.reference * (
                1 + (-1 if pos > 0 else 1) * self.entry_pct
            )
            entry_args.append(
                {
                    "code": code,
                    "pos": pos,
                    "entry_price": {price_round(entry_price, pos > 0): pos},
                    "stop_profit_price": {price_round(stop_profit_price, pos < 0): pos},
                    "stop_loss_price": {price_round(stop_loss_price, pos > 0): pos},
                }
            )
        return entry_args
