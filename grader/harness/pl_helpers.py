def name(label):
    def decorator(fn):
        fn._pl_name = label
        return fn

    return decorator
