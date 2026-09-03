def is_palindrome(s):
    s = s.lower()
    for i in range(len(s) // 2):
        if s[i] != s[len(s) - 1 - i]:
            return False
    return True


def parse_int(s):
    try:
        return int(s)
    except ValueError:
        raise ValueError(f"not a valid integer: {s!r}")
