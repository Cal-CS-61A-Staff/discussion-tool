import re


def normalize_and_compare(prediction, expected):
    return _normalize(prediction) == _normalize(expected)


def _normalize(text):
    # Case-insensitive: expected values now include category words like
    # "Function" (build_prediction_feedback below) that a student could
    # reasonably type in any case.
    return re.sub(r"\s+", "", text or "").lower()


def build_prediction_feedback(call, student_prediction, predict_result):
    """`predict_result` is the sandbox's report of what the student's own
    code actually did for `call` (grader/harness/runner.py:
    _evaluate_predict_call) — None if this question has no prediction quiz
    at all.

    A real error (the call raised, or the student's code didn't even load)
    is shown outright as a traceback regardless of what was predicted —
    that's a bug worth surfacing, not something to make them trace through.
    A plain value mismatch instead hides the actual value, so getting it
    wrong doesn't just hand them the answer.
    """
    if predict_result is None:
        return None

    if predict_result["kind"] == "error":
        return {
            "call": call,
            "got": student_prediction,
            "is_error": True,
            "traceback": predict_result["traceback"],
        }

    expected = "Function" if predict_result["kind"] == "function" else predict_result["repr"]
    return {
        "call": call,
        "expected": expected,
        "got": student_prediction,
        "is_error": False,
        "is_match": normalize_and_compare(student_prediction, expected),
    }
