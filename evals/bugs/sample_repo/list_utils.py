def moving_average(nums, window):
    if window <= 0 or window > len(nums):
        raise ValueError("window must be between 1 and len(nums)")
    return [sum(nums[i:i + window]) / window for i in range(len(nums) - window + 1)]


def chunk_list(lst, size):
    if size <= 0:
        raise ValueError("size must be positive")
    return [lst[i:i + size] for i in range(0, len(lst), size)]


def get_nth_from_end(lst, n):
    if n <= 0 or n > len(lst):
        raise IndexError("n out of range")
    return lst[len(lst) - n]


def paginate(items, page, page_size):
    if page <= 0:
        raise ValueError("page must be 1 or greater")
    pages = chunk_list(items, page_size)
    if page > len(pages):
        raise IndexError("page out of range")
    return pages[page - 1]
