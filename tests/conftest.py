import pytest
import shioaji as sj
from pytest_mock import MockFixture


@pytest.fixture
def api(mocker: MockFixture) -> sj.Shioaji:
    return mocker.MagicMock()
