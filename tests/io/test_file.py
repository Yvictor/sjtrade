import pytest
from pytest_mock import MockFixture
from sjtrade.io.file import read_position


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
