import pytest

from string_utils import is_palindrome, parse_int


def test_is_palindrome_detects_non_palindromes():
    assert is_palindrome("abba") is True
    assert is_palindrome("abca") is False


def test_parse_int_raises_value_error_on_bad_input():
    with pytest.raises(ValueError):
        parse_int("not-a-number")
