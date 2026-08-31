"""server/services/compare.py — the prediction-quiz comparison, and
build_prediction_feedback which turns the sandbox's report of what the
student's own code actually did (grader/harness/runner.py:
_evaluate_predict_call) into what the frontend shows.
"""

from server.services import compare


def test_normalize_and_compare_ignores_whitespace_and_case():
    assert compare.normalize_and_compare("  16 ", "16") is True
    assert compare.normalize_and_compare("Function", "function") is True
    assert compare.normalize_and_compare("16", "17") is False


def test_build_prediction_feedback_returns_none_without_a_predict_result():
    assert compare.build_prediction_feedback("f(5)", "16", None) is None


def test_build_prediction_feedback_matches_a_correct_value_prediction():
    feedback = compare.build_prediction_feedback("f(5)", "16", {"kind": "value", "repr": "16"})
    assert feedback == {
        "call": "f(5)",
        "expected": "16",
        "got": "16",
        "is_error": False,
        "is_match": True,
    }


def test_build_prediction_feedback_flags_a_wrong_value_prediction():
    feedback = compare.build_prediction_feedback("f(5)", "17", {"kind": "value", "repr": "16"})
    assert feedback["is_match"] is False
    # The actual value is still present in the payload — server/blueprints/
    # groups.py doesn't strip it, GraderFeedbackPanel.jsx is what hides it
    # from a student who got it wrong, so the panel can still show the
    # right answer once they *do* get it right on a later attempt.
    assert feedback["expected"] == "16"


def test_build_prediction_feedback_shows_function_instead_of_a_raw_repr():
    # "Function" is a literal category label, matched exactly (modulo case/
    # whitespace) like any other expected value -- not fuzzy-matched
    # against prose like "a function".
    feedback = compare.build_prediction_feedback("f(5)", "function", {"kind": "function"})
    assert feedback["expected"] == "Function"
    assert feedback["is_match"] is True


def test_build_prediction_feedback_surfaces_a_real_error_regardless_of_the_guess():
    feedback = compare.build_prediction_feedback("f(5)", "16", {"kind": "error", "traceback": "Traceback...\nValueError: oops"})
    assert feedback["is_error"] is True
    assert feedback["traceback"] == "Traceback...\nValueError: oops"
    assert "is_match" not in feedback
    assert "expected" not in feedback
