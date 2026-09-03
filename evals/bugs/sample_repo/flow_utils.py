def classify(n):
    if n > 0:
        label = "positive"
    elif n < 0:
        label = "negative"
    else:
        label = "zero"
    return label


def sum_positive(nums):
    total = 0
    for n in nums:
        if n > 0:
            total += n
    return total


def first_match(items, predicate):
    result = None
    for item in items:
        if predicate(item):
            result = item
            break
    return result
