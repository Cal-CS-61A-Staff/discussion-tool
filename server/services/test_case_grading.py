"""Generates a PLTestCase test_code.py from TA-authored {call, expected}
pairs (server/models/worksheet.py:Question.test_cases_json, authored via
the guided question form) — reuses the existing grader harness
(grader/harness/pl_unit_test.py, code_feedback.py) exactly as it already
works for the hand-authored tree worksheet, rather than adding a new
container-side grading mode.
"""


def generate_simple_test_code(test_cases):
    lines = [
        "from pl_unit_test import PLTestCase",
        "from pl_helpers import name",
        "from code_feedback import Feedback",
        "",
        "",
        "class Test(PLTestCase):",
    ]
    for i, case in enumerate(test_cases):
        call = case["call"]
        expected = case["expected"]
        lines += [
            "",
            f"    @name({call!r})",
            f"    def test_{i}(self):",
            "        try:",
            f"            actual = str(eval({call!r}, dict(vars(self.st))))",
            "        except Exception as e:",
            "            actual = '{0}: {1}'.format(type(e).__name__, e)",
            f"        if Feedback.check_scalar({call!r}, {expected!r}, actual):",
            "            Feedback.set_score(1)",
            "        else:",
            "            Feedback.set_score(0)",
        ]
    return "\n".join(lines) + "\n"
