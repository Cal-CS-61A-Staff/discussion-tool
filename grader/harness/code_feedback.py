class Feedback:
    """Minimal analog of PrairieLearn's code_feedback.Feedback.

    `_current` points at whichever PLTestCase instance is running right now
    (set in PLTestCase.setUp) so that test authors can call `Feedback.set_score(...)`
    and `Feedback.check_scalar(...)` as bare classmethods, matching PrairieLearn's
    actual test-authoring API, without threading `self` through every call.
    """

    _current = None

    @classmethod
    def set_score(cls, score):
        if cls._current is None:
            raise RuntimeError('Feedback.set_score() called outside of a running test')
        cls._current._score = max(0.0, min(1.0, float(score)))

    @classmethod
    def check_scalar(cls, label, expected, actual, report_failure=True):
        ok = expected == actual
        if not ok and report_failure and cls._current is not None:
            cls._current._messages.append('{0}: expected {1!r}, got {2!r}'.format(label, expected, actual))
        return ok

    @classmethod
    def check_list(cls, label, expected, actual, report_failure=True):
        ok = list(expected) == list(actual)
        if not ok and report_failure and cls._current is not None:
            cls._current._messages.append('{0}: expected {1!r}, got {2!r}'.format(label, expected, actual))
        return ok

    @classmethod
    def check_tuple(cls, label, expected, actual, report_failure=True):
        ok = tuple(expected) == tuple(actual)
        if not ok and report_failure and cls._current is not None:
            cls._current._messages.append('{0}: expected {1!r}, got {2!r}'.format(label, expected, actual))
        return ok

    @classmethod
    def not_allowed(cls, *args, **kwargs):
        raise RuntimeError('This function is not allowed to be used in this question.')
