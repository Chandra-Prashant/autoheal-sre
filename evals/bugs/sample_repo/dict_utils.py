def get_item(d, key):
    try:
        return d[key]
    except KeyError:
        raise KeyError(f"missing key: {key!r}")


def merge_dicts(a, b):
    if b is None:
        b = {}
    merged = dict(a)
    merged.update(b)
    return merged


def get_config_value(config, key, default=None):
    if config is None:
        return default
    return config.get(key, default)
