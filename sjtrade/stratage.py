import shioaji as sj
from loguru import logger
from .io.file import read_position
from .utils import price_round


class StratageBase:
    name: str

    def entry_positions(self):
        raise NotImplementedError()

    def cover_positions(self):
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
                    "entry_price": {price_round(entry_price, pos > 0): pos},
                    "stop_profit_price": {price_round(stop_profit_price, pos < 0): pos},
                    "stop_loss_price": {price_round(stop_loss_price, pos > 0): pos},
                }
            )
        return entry_args
