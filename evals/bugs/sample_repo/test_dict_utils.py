import pytest

from dict_utils import get_config_value, get_item, merge_dicts


def test_get_item_raises_key_error_for_missing_key():
    with pytest.raises(KeyError):
        get_item({"a": 1}, "b")


def test_merge_dicts_treats_none_as_empty():
    assert merge_dicts({"a": 1}, None) == {"a": 1}


def test_get_config_value_returns_default_when_config_is_none():
    assert get_config_value(None, "timeout", 30) == 30
