import pytest

from stack import Stack


def test_pop_from_empty_stack_raises_index_error():
    with pytest.raises(IndexError):
        Stack().pop()
