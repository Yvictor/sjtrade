""" sjtrade
trading with shioaji
"""

__version__ = "0.4.6"

def inject_env():
    import os

    if os.environ.get("LOGURU_FORMAT", None) is None:
        os.environ["LOGURU_FORMAT"] = (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green>"
            " | <level>{level: <8}</level>"
            " | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan>"
            " | <level>{message}</level>"
        )

inject_env()
from .trader import SJTrader
from .strategy import StrategyBase
