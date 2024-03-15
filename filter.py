_filters = []


def apply_filters(ctx_msg):
    filters = sorted(_filters, key=lambda x: x[0], reverse=True)
    for f in filters:
        r = f[1](ctx_msg)
        if r is False:
            return False
    return True


def add_filter(func, priority=0):
    _filters.append((priority, func))
