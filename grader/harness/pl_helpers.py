def points(value):
    def decorator(fn):
        fn._pl_points = value
        return fn

    return decorator


def name(label):
    def decorator(fn):
        fn._pl_name = label
        return fn

    return decorator
