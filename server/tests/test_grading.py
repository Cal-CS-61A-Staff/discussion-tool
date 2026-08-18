"""Integration tests against the real `discussion-grader` Docker image —
deliberately not mocked, since the whole point is verifying the sandbox
actually contains untrusted code (see grader/ at the repo root). Requires
`docker build -t discussion-grader:latest ./grader` to have been run first.
"""

import shutil

import pytest

from server.services import grading

pytestmark = pytest.mark.skipif(shutil.which("docker") is None, reason="docker not available")

SETUP_CODE = """
class Tree:
    def __init__(self, label, branches=[]):
        self.label = label
        self.branches = list(branches)
"""

TEST_CODE = """
from pl_unit_test import PLTestCase
from pl_helpers import name, points
from code_feedback import Feedback


class Test(PLTestCase):
    @points(1)
    @name("basic")
    def test_0(self):
        actual = self.st.tree_sum(self.st.Tree(1, [self.st.Tree(2), self.st.Tree(3)]))
        if Feedback.check_scalar("tree_sum(...)", 6, actual):
            Feedback.set_score(1)
        else:
            Feedback.set_score(0)

    @points(1)
    @name("leaf")
    def test_1(self):
        actual = self.st.tree_sum(self.st.Tree(5))
        if Feedback.check_scalar("tree_sum(Tree(5))", 5, actual):
            Feedback.set_score(1)
        else:
            Feedback.set_score(0)
"""


DOCTEST_CODE = '''
def hailstone(n):
    """Print the hailstone sequence starting at n and return its number of steps.

    >>> a = hailstone(10)
    10
    5
    16
    8
    4
    2
    1
    >>> a
    7
    """
'''


class FakeQuestion:
    def __init__(self, setup_code="", test_code="", grading_mode="pltest"):
        self.setup_code = setup_code
        self.test_code = test_code
        self.grading_mode = grading_mode


@pytest.fixture()
def question():
    return FakeQuestion(SETUP_CODE, TEST_CODE)


def test_correct_submission_passes_all(question):
    code = "def tree_sum(t):\n    return t.label + sum([tree_sum(b) for b in t.branches])\n"
    result = grading.run_grader(question, code)

    assert result["error"] is None
    assert result["passed_count"] == 2
    assert result["total_count"] == 2
    assert result["total_points"] == 2


def test_wrong_submission_reports_partial_failure(question):
    code = "def tree_sum(t):\n    return t.label\n"
    result = grading.run_grader(question, code)

    assert result["error"] is None
    assert result["passed_count"] == 1
    assert result["total_count"] == 2
    failed = [t for t in result["test_results"] if not t["passed"]]
    assert len(failed) == 1
    assert "expected 6" in failed[0]["message"]


def test_broken_submission_reports_error_not_crash(question):
    code = "def tree_sum(t):\n    raise ValueError('oops')\n"
    result = grading.run_grader(question, code)

    assert result["error"] is None
    assert result["passed_count"] == 0
    assert all("ValueError" in t["message"] for t in result["test_results"])


def test_code_that_fails_to_even_define_the_function(question):
    code = "this is not valid python !!!\n"
    result = grading.run_grader(question, code)

    assert result["error"] is not None
    assert result["passed_count"] == 0


def test_malicious_code_cannot_read_deleted_test_file(question):
    code = (
        "try:\n"
        "    with open('/grade/work/test_code.py') as f:\n"
        "        leaked = f.read()\n"
        "except Exception as e:\n"
        "    leaked = None\n"
        "print('LEAK:', leaked)\n"
        "def tree_sum(t):\n"
        "    return t.label + sum([tree_sum(b) for b in t.branches])\n"
    )
    result = grading.run_grader(question, code)

    assert result["error"] is None
    assert "LEAK: None" in result["student_output"]
    assert "class Test" not in result["student_output"]


def test_student_print_does_not_corrupt_result_channel(question):
    code = (
        "print('debug output', end='')\n"
        "def tree_sum(t):\n"
        "    return t.label + sum([tree_sum(b) for b in t.branches])\n"
    )
    result = grading.run_grader(question, code)

    assert result["error"] is None
    assert result["passed_count"] == 2
    assert "debug output" in result["student_output"]


def test_infinite_loop_times_out_and_cleans_up_container(question, monkeypatch):
    import subprocess

    from server.config import Config

    monkeypatch.setattr(Config, "GRADER_CONTAINER_TIMEOUT_SECONDS", 3)
    code = "def tree_sum(t):\n    while True:\n        pass\n"

    result = grading.run_grader(question, code)

    assert result["error"] is not None
    assert "timed out" in result["error"].lower()

    leftover = subprocess.run(
        ["docker", "ps", "-a", "-q", "--filter", "ancestor=discussion-grader:latest"],
        capture_output=True,
        text=True,
    )
    assert leftover.stdout.strip() == "", "grading container was not cleaned up after timeout"


@pytest.fixture()
def doctest_question():
    return FakeQuestion(grading_mode="doctest")


def test_doctest_mode_correct_submission_passes_all(doctest_question):
    code = (
        DOCTEST_CODE
        + """
    steps = 0
    while n != 1:
        print(n)
        steps += 1
        n = n // 2 if n % 2 == 0 else 3 * n + 1
    print(n)
    steps += 1
    return steps
"""
    )
    result = grading.run_grader(doctest_question, code)

    assert result["error"] is None
    assert result["total_count"] == 2
    assert result["passed_count"] == 2


def test_doctest_mode_wrong_submission_reports_failing_example(doctest_question):
    code = (
        DOCTEST_CODE
        + """
    steps = 0
    while n != 1:
        print(n)
        steps += 1
        n = n // 2 if n % 2 == 0 else 3 * n + 1
    print(n)
    return steps
"""
    )
    result = grading.run_grader(doctest_question, code)

    assert result["error"] is None
    assert result["passed_count"] == 1
    assert result["total_count"] == 2
    failed = [t for t in result["test_results"] if not t["passed"]]
    assert len(failed) == 1
    assert "expected '7'" in failed[0]["message"]


def test_doctest_mode_exception_reports_failure_not_crash(doctest_question):
    # `a = hailstone(10)` raises immediately, so `a` is never bound — the
    # second example correctly fails too, but with NameError, not
    # RuntimeError. Both are still reported (not a crash), which is the
    # actual thing under test here.
    code = DOCTEST_CODE + "\n    raise RuntimeError('nope')\n"
    result = grading.run_grader(doctest_question, code)

    assert result["error"] is None
    assert result["passed_count"] == 0
    assert result["total_count"] == 2
    assert all(not t["passed"] and t["message"] for t in result["test_results"])
    assert "RuntimeError" in result["test_results"][0]["message"]
