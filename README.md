# sjtrade

[![PyPI](https://img.shields.io/pypi/v/sjtrade)](https://pypi.org/project/sjtrade/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Test and Deploy](https://github.com/Yvictor/sjtrade/actions/workflows/test-deploy.yml/badge.svg)](https://github.com/Yvictor/sjtrade/actions/workflows/test-deploy.yml)
[![codecov](https://codecov.io/gh/Yvictor/sjtrade/branch/master/graph/badge.svg?token=hHZzwJEPyt)](https://codecov.io/gh/Yvictor/sjtrade)
[![Telegram](https://img.shields.io/badge/chat-%20telegram-blue.svg)](https://t.me/joinchat/973EyAQlrfthZTk1)
[![Open Tutorial In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/yvictor/sjtrade/blob/master/tutorial/quickstart.ipynb)

shioaji day trading demo package


## Install
```
pip install sjtrade
```
## Get started

### Init Shioaji and SjTrader
``` python
import shioaji as sj
import sjtrade

api = sj.Shioaji()
accounts = api.login(**login_kws)
sjtrader = sjtrade.SJTrader(api)
```

### Set Position Filepath and Preview Position
``` python
sjtrader.position_filepath = "position.txt"
sjtrade.io.file.read_position(sjtrader.position_filepath)
```

### Set Custom Position FileReader
``` python
from sjtrade.io.file import read_csv_position
sjtrader.read_position_func = read_csv_position
sjtrader.position_filepath = "position.csv"
sjtrader.read_position_func(sjtrader.position_filepath)
```

### Set entry_pct stop_profit_pct stop_loss_pct
``` python
sjtrader.entry_pct = 0.05
sjtrader.stop_profit_pct = 0.095
sjtrader.stop_loss_pct = 0.09
```

### Start sjtrader
``` python
sjtrader.start()
```

### What do sjtrader start actually do
``` ipython
sjtrader.start??
```

```
Signature: sjtrader.start()
Source:   
    def start(self):
        positions = read_position(self._position_filepath)
        self.api.set_order_callback(self.order_deal_handler)
        sleep_until(8, 45)
        self.place_entry_order(positions, self.entry_pct)
        sleep_until(8, 54, 59)
        self.api.quote.set_on_tick_stk_v1_callback(self.cancel_preorder_handler)
        sleep_until(8, 59, 55)
        self.api.quote.set_on_tick_stk_v1_callback(self.intraday_handler)
        sleep_until(13, 25, 59)
        self.open_position_cover()
File:      ~/.pyenv/versions/miniconda3-latest/lib/python3.7/site-packages/sjtrade/trader.py
Type:      method
```

### Simulation
all order will be place as success and deal when price touch
```
api = sj.Shioaji()
accounts = api.login(**login_kws)
sjtrader = sjtrade.SJTrader(api, simulation=True)
sjtrader.position_filepath = "position.txt"
sjtrade.io.file.read_position(sjtrader.position_filepath)
sjtrader.entry_pct = 0.05
sjtrader.stop_profit_pct = 0.095
sjtrader.stop_loss_pct = 0.09
sjtrader.start()
```

### Notifications 
``` bash
pip install notifiers
```

#### Check notifiers
``` python
from notifiers import get_notifier
notifier = get_notifier("telegram")
TELECHATID = ""
TELEBOT_TOKEN = ""
PARAMS = {"chat_id": TELECHATID, "token": TELEBOT_TOKEN}
notifier.notify(message="test", **PARAMS)
```

#### Check logger
``` python
from loguru import logger
from notifiers.logging import NotificationHandler
handler = NotificationHandler("telegram", defaults=PARAMS)
logger.add(handler, level="INFO")
logger.info("logger test")
```


## Developer's guide

```
flit install -s
```