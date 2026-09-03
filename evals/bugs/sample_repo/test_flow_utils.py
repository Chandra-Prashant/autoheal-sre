from flow_utils import classify, first_match, sum_positive


def test_classify_handles_zero():
    assert classify(0) == "zero"


def test_sum_positive_adds_positive_numbers():
    assert sum_positive([1, -2, 3, -4, 5]) == 9


def test_first_match_returns_none_when_nothing_matches():
    assert first_match([1, 2, 3], lambda x: x > 10) is None
