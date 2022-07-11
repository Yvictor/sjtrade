import loguru
import pytest
import shioaji as sj
from pytest_mock import MockFixture


@pytest.fixture
def stock_contracts_raw():
    return [
        {
            "security_type": "STK",
            "exchange": "TSE",
            "code": "1605",
            "symbol": "TSE1605",
            "name": "華新",
            "currency": "TWD",
            "unit": 1000,
            "limit_up": 43.3,
            "limit_down": 35.5,
            "reference": 39.4,
            "update_date": "2022/05/19",
            "margin_trading_balance": 29297,
            "short_selling_balance": 1596,
            "day_trade": "Yes",
        },
        {
            "security_type": "STK",
            "exchange": "OTC",
            "code": "6290",
            "symbol": "OTC6290",
            "name": "良維",
            "currency": "TWD",
            "unit": 1000,
            "limit_up": 63.0,
            "limit_down": 51.6,
            "reference": 57.3,
            "update_date": "2022/05/19",
            "margin_trading_balance": 354,
            "short_selling_balance": 144,
            "day_trade": "Yes",
        },
    ]


@pytest.fixture
def api(mocker: MockFixture, stock_contracts_raw: list) -> sj.Shioaji:
    mock_api = mocker.MagicMock()
    mock_api.Contracts = sj.contracts.Contracts()
    stream_contracts = sj.contracts.StreamStockContracts(stock_contracts_raw)
    mock_api.Contracts.Stocks.append(stream_contracts)
    mock_api.Contracts.Indexs.set_status_fetched()
    mock_api.Contracts.Stocks.set_status_fetched()
    mock_api.Contracts.Futures.set_status_fetched()
    mock_api.Contracts.Options.set_status_fetched()
    mock_api.Contracts.status = sj.contracts.FetchStatus.Fetched
    return mock_api


@pytest.fixture
def api(mocker: MockFixture, stock_contracts_raw: list) -> sj.Shioaji:
    mock_api = mocker.MagicMock()
    mock_api.Contracts = sj.contracts.Contracts()
    stream_contracts = sj.contracts.StreamStockContracts(stock_contracts_raw)
    mock_api.Contracts.Stocks.append(stream_contracts)
    mock_api.Contracts.Indexs.set_status_fetched()
    mock_api.Contracts.Stocks.set_status_fetched()
    mock_api.Contracts.Futures.set_status_fetched()
    mock_api.Contracts.Options.set_status_fetched()
    mock_api.Contracts.status = sj.contracts.FetchStatus.Fetched
    return mock_api


@pytest.fixture
def logger(mocker: MockFixture) -> loguru._logger.Logger:
    return mocker.patch("sjtrade.trader.logger")


@pytest.fixture
def logger_stratagy(mocker: MockFixture) -> loguru._logger.Logger:
    return mocker.patch("sjtrade.strategy.logger")
