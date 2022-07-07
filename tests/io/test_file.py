import pytest
from pytest_mock import MockFixture
from sjtrade.io.file import read_csv_position, read_position


def test_read_position(mocker: MockFixture):
    mocker.patch("pathlib.Path.is_file").return_value = True
    mocker.patch("pathlib.Path.exists").return_value = True
    mocker.patch(
        "pathlib.Path.read_text"
    ).return_value = "1524\t18.0\n2359\t10.0\n3141\t2.0\n3265\t6.0\n4133\t6.0\n5608\t6.0\n6104\t1.0\n6470\t4.0\n"
    res = read_position("position.txt")
    assert res == {
        "1524": 18,
        "2359": 10,
        "3141": 2,
        "3265": 6,
        "4133": 6,
        "5608": 6,
        "6104": 1,
        "6470": 4,
    }


def test_read_position_notfile():
    with pytest.raises(FileNotFoundError):
        read_position("")


def test_read_csv_position(mocker: MockFixture):
    mocker.patch("pathlib.Path.is_file").return_value = True
    mocker.patch("pathlib.Path.exists").return_value = True
    mocker.patch(
        "pathlib.Path.read_text"
    ).return_value = (
        "標的,張數,停損檔數,尾盤鋪單%數\n1319,-8,3,1\n1539,-9,3,1\n1760,-9,4,2\n1795,-9,2,1\n"
    )
    res = read_csv_position("position.csv")
    assert res == {
        "1319": {"pos": -8, "stop_loss_tick": 3, "cover_pct": 1},
        "1539": {"pos": -9, "stop_loss_tick": 3, "cover_pct": 1},
        "1760": {"pos": -9, "stop_loss_tick": 4, "cover_pct": 2},
        "1795": {"pos": -9, "stop_loss_tick": 2, "cover_pct": 1},
    }


def test_read_position_notfile():
    with pytest.raises(FileNotFoundError):
        read_csv_position("")
