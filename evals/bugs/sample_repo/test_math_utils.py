import pytest

from math_utils import divide


def test_divide_by_zero_raises_zero_division_error():
    with pytest.raises(ZeroDivisionError):
        divide(10, 0)
