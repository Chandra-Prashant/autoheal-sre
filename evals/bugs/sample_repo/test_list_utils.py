from list_utils import chunk_list, get_nth_from_end, moving_average, paginate


def test_moving_average_covers_every_window():
    assert moving_average([1, 2, 3, 4], 2) == [1.5, 2.5, 3.5]


def test_chunk_list_splits_evenly():
    assert chunk_list([1, 2, 3, 4, 5, 6], 3) == [[1, 2, 3], [4, 5, 6]]


def test_get_nth_from_end_returns_correct_element():
    assert get_nth_from_end([10, 20, 30, 40, 50], 1) == 50
    assert get_nth_from_end([10, 20, 30, 40, 50], 2) == 40


def test_paginate_returns_the_requested_page():
    items = list(range(1, 10))
    assert paginate(items, page=1, page_size=3) == [1, 2, 3]
    assert paginate(items, page=3, page_size=3) == [7, 8, 9]
