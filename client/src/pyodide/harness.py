"""In-browser grading harness — a port of server-side grader/harness/ to
run under Pyodide in a Web Worker. Two modes:

  doctest  — run the >>> examples in the student's own docstrings
  pltest   — run a `class Test(PLTestCase)` from test_code

`grade(setup_code, student_code, test_code, mode)` returns a dict shaped
exactly like the old Docker grader's JSON result:
  {test_results: [...], passed_count, total_count, error, student_output}

`run_call(context_code, call)` evaluates a single expression against
context_code's namespace and reports what it displayed — used for the
prediction prompt and counterexample grading.

No filesystem, no env vars, no network (Pyodide has none by default).
"""

import contextlib
import doctest
import io
import sys
import traceback
import types
import unittest
from types import SimpleNamespace


# --- code_feedback.Feedback -------------------------------------------------
class Feedback:
    _current = None

    @classmethod
    def set_score(cls, score):
        if cls._current is None:
            raise RuntimeError("Feedback.set_score() called outside of a running test")
        cls._current._score = max(0.0, min(1.0, float(score)))

    @classmethod
    def check_scalar(cls, label, expected, actual, report_failure=True):
        ok = expected == actual
        if not ok and report_failure and cls._current is not None:
            cls._current._messages.append("{0}: expected {1!r}, got {2!r}".format(label, expected, actual))
        return ok

    @classmethod
    def check_list(cls, label, expected, actual, report_failure=True):
        ok = list(expected) == list(actual)
        if not ok and report_failure and cls._current is not None:
            cls._current._messages.append("{0}: expected {1!r}, got {2!r}".format(label, expected, actual))
        return ok

    @classmethod
    def check_tuple(cls, label, expected, actual, report_failure=True):
        ok = tuple(expected) == tuple(actual)
        if not ok and report_failure and cls._current is not None:
            cls._current._messages.append("{0}: expected {1!r}, got {2!r}".format(label, expected, actual))
        return ok

    @classmethod
    def not_allowed(cls, *args, **kwargs):
        raise RuntimeError("This function is not allowed to be used in this question.")


# --- pl_helpers.name ------------------------------------------------------
def name(label):
    def decorator(fn):
        fn._pl_name = label
        return fn

    return decorator


# --- pl_unit_test.PLTestCase -------------------------------------------------
class PLTestCase(unittest.TestCase):
    st = None

    def setUp(self):
        self._score = 0.0
        self._messages = []
        Feedback._current = self


# Hand-authored (and 'simple'-generated) test_code opens with
#   from pl_unit_test import PLTestCase
#   from pl_helpers import name
#   from code_feedback import Feedback
# just as it did against the old grader/harness/ package on sys.path.
# Register the same names as importable modules so that keeps working.
for _mod_name, _attrs in (
    ("pl_unit_test", {"PLTestCase": PLTestCase}),
    ("pl_helpers", {"name": name}),
    ("code_feedback", {"Feedback": Feedback}),
):
    _mod = types.ModuleType(_mod_name)
    for _k, _v in _attrs.items():
        setattr(_mod, _k, _v)
    sys.modules[_mod_name] = _mod


# --- doctest mode --------------------------------------------------------
class _RecordingDocTestRunner(doctest.DocTestRunner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []

    def report_success(self, out, test, example, got):
        self.records.append({"name": example.source.strip(), "passed": True, "message": None})

    def report_failure(self, out, test, example, got):
        message = "expected {0!r}, got {1!r}".format(example.want.strip(), got.strip())
        self.records.append({"name": example.source.strip(), "passed": False, "message": message})

    def report_unexpected_exception(self, out, test, example, exc_info):
        message = "raised {0}: {1}".format(exc_info[0].__name__, exc_info[1])
        self.records.append({"name": example.source.strip(), "passed": False, "message": message})


def _run_doctests(module):
    finder = doctest.DocTestFinder()
    tests = finder.find(module, module.__name__, module=module)
    runner = _RecordingDocTestRunner(optionflags=doctest.NORMALIZE_WHITESPACE)
    for test in tests:
        if test.examples:
            runner.run(test)
    return [
        {"name": r["name"][:80], "passed": r["passed"], "message": r["message"]}
        for r in runner.records
    ]


# --- pltest mode -------------------------------------------------------
def _run_test_method(test_class, method_name, student_namespace):
    test_class.st = SimpleNamespace(**student_namespace)
    method = getattr(test_class, method_name)
    label = getattr(method, "_pl_name", method_name)
    instance = test_class(method_name)
    try:
        instance.setUp()
        getattr(instance, method_name)()
        message = "; ".join(instance._messages) if instance._messages else None
        passed = instance._score >= 1.0
    except AssertionError as e:
        message = str(e) or "assertion failed"
        passed = False
    except Exception as e:  # noqa: BLE001 - untrusted code can raise anything
        message = "{0}: {1}".format(type(e).__name__, e)
        passed = False
    return {"name": label, "passed": passed, "message": message}


# --- prediction / counterexample: evaluate one expression -----------------
def run_call(context_code, call):
    """Runs `context_code` then evaluates `call`, capturing what it
    displays. Returns:
      {"kind": "value", "repr": str}   -- bare expr's repr / what it printed
      {"kind": "function"}             -- displayed something callable
      {"kind": "error", "traceback": str}
    """
    ns = {}
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(context_code or "", "context", "exec"), ns)  # noqa: S102 - untrusted, sandboxed by Pyodide
    except Exception:  # noqa: BLE001
        return {"kind": "error", "traceback": traceback.format_exc()}

    lines = [ln for ln in (call or "").splitlines() if ln.strip()]
    if not lines:
        return {"kind": "value", "repr": "None"}
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            for ln in lines[:-1]:
                exec(compile(ln, "call", "single"), ns)  # noqa: S102
        displayed = []
        original = sys.displayhook

        def _hook(value):
            if value is not None:
                displayed.append(value)
            original(value)

        captured = io.StringIO()
        try:
            sys.displayhook = _hook
            with contextlib.redirect_stdout(captured):
                exec(compile(lines[-1], "call", "single"), ns)  # noqa: S102
        finally:
            sys.displayhook = original
    except Exception:  # noqa: BLE001
        return {"kind": "error", "traceback": traceback.format_exc()}

    if displayed and callable(displayed[-1]):
        return {"kind": "function"}
    out = captured.getvalue().rstrip("\n")
    return {"kind": "value", "repr": out if out else "None"}


# --- entrypoint --------------------------------------------------------
def _exec_all(setup_code, student_code, ns, captured):
    with contextlib.redirect_stdout(captured):
        exec(compile(setup_code or "", "setup_code.py", "exec"), ns)  # noqa: S102
        exec(compile(student_code or "", "student_code.py", "exec"), ns)  # noqa: S102


def grade(setup_code, student_code, test_code, mode):
    result = {"test_results": [], "passed_count": 0, "total_count": 0, "error": None, "student_output": ""}
    captured = io.StringIO()

    if mode == "doctest":
        module = types.ModuleType("student_code")
        try:
            _exec_all(setup_code, student_code, module.__dict__, captured)
        except Exception as e:  # noqa: BLE001
            result["error"] = "Your code raised an error before any tests could run: {0}: {1}".format(
                type(e).__name__, e
            )
            result["student_output"] = captured.getvalue()
            return result
        with contextlib.redirect_stdout(captured):
            test_results = _run_doctests(module)
    else:  # pltest
        ns = {}
        try:
            _exec_all(setup_code, student_code, ns, captured)
        except Exception as e:  # noqa: BLE001
            result["error"] = "Your code raised an error before any tests could run: {0}: {1}".format(
                type(e).__name__, e
            )
            result["student_output"] = captured.getvalue()
            return result
        test_ns = {}
        try:
            exec(compile(test_code or "", "test_code.py", "exec"), test_ns)  # noqa: S102
            test_class = test_ns["Test"]
        except Exception as e:  # noqa: BLE001
            result["error"] = "Internal grading error (bad test definition): {0}".format(e)
            return result
        method_names = sorted(
            m for m in dir(test_class) if m.startswith("test_") and callable(getattr(test_class, m))
        )
        with contextlib.redirect_stdout(captured):
            test_results = [_run_test_method(test_class, m, ns) for m in method_names]

    for tr in test_results:
        result["test_results"].append(tr)
        result["total_count"] += 1
        if tr["passed"]:
            result["passed_count"] += 1
    result["student_output"] = captured.getvalue()
    return result
