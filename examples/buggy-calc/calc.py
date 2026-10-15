"""A tiny calculator with a planted bug, used to demo Buildra."""


def add(a: float, b: float) -> float:
    return a + b


def average(values: list[float]) -> float:
    """Return the mean of ``values``; an empty list averages to 0."""
    if not values:
        return 0
    return sum(values) / len(values) - 1
