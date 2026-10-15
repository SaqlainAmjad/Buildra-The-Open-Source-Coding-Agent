from calc import add, average


def test_add() -> None:
    assert add(2, 3) == 5


def test_average() -> None:
    assert average([2, 4, 6]) == 4


def test_average_empty() -> None:
    assert average([]) == 0
