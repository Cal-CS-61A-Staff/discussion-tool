"""Runs as the unprivileged `ag` user (see run.sh). Loads the setup code and
(for pltest mode) test code into memory, deletes both from disk (so student
code — which runs in this same process — can't read the test definitions off
disk once it's running), execs setup+student code, then grades via one of
two modes selected by the GRADING_MODE env var:

  pltest (default) — runs each test_* method of a `class Test(PLTestCase)`
  defined in test_code.py (see pl_unit_test.py, code_feedback.py).

  doctest — runs the >>> examples already present in the student's own
  function docstrings (see doctest_runner.py); test_code.py is unused.

If PL_PREDICT_CALL is set (the prediction-quiz call, TA/content-authored —
never student input, so evaluating it here is no different a risk than
running the student's own code, which this process already does), it's
evaluated against the student's own definitions after they load — the whole
point being to grade the student's *prediction* against what their own code
actually does, bugs included, not against a reference solution.
"""

import contextlib
import io
import json
import os
import sys
import traceback
import types
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from doctest_runner import run_doctests  # noqa: E402

WORK_DIR = '/grade/work'
RESULTS_DIR = '/grade/results'


def main():
    grading_mode = os.environ.get('GRADING_MODE', 'pltest')
    predict_call = os.environ.get('PL_PREDICT_CALL') or None
    secret_filename = os.environ['PL_RESULT_FILENAME']
    result = {
        'test_results': [],
        'passed_count': 0,
        'total_count': 0,
        'error': None,
        'student_output': '',
        'predict_result': None,
    }

    setup_path = os.path.join(WORK_DIR, 'setup_code.py')
    test_path = os.path.join(WORK_DIR, 'test_code.py')
    student_path = os.path.join(WORK_DIR, 'student_code.py')

    with open(setup_path) as f:
        setup_code = f.read()
    with open(test_path) as f:
        test_code = f.read()
    with open(student_path) as f:
        student_code = f.read()

    # Sensitive files removed from disk before student code ever runs.
    os.remove(setup_path)
    os.remove(test_path)

    captured = io.StringIO()

    if grading_mode == 'doctest':
        # doctest.DocTestFinder needs a real module object (it introspects
        # __dict__ for functions/classes with docstrings), not a plain dict.
        module = types.ModuleType('student_code')
        try:
            _exec_setup_and_student(setup_code, student_code, module.__dict__, captured)
        except Exception as e:  # noqa: BLE001 - untrusted code
            result['error'] = 'Your code raised an error before any tests could run: {0}: {1}'.format(
                type(e).__name__, e
            )
            result['predict_result'] = _predict_result_for_exec_failure()
            result['student_output'] = captured.getvalue()
            write_results(secret_filename, result)
            return

        result['predict_result'] = _evaluate_predict_call(predict_call, module.__dict__)

        with contextlib.redirect_stdout(captured):
            test_results = run_doctests(module)

        _accumulate(result, test_results)
        result['student_output'] = captured.getvalue()
        write_results(secret_filename, result)
        return

    # pltest mode.
    namespace = {}
    try:
        _exec_setup_and_student(setup_code, student_code, namespace, captured)
    except Exception as e:  # noqa: BLE001 - untrusted code
        result['error'] = 'Your code raised an error before any tests could run: {0}: {1}'.format(
            type(e).__name__, e
        )
        result['predict_result'] = _predict_result_for_exec_failure()
        result['student_output'] = captured.getvalue()
        write_results(secret_filename, result)
        return

    result['predict_result'] = _evaluate_predict_call(predict_call, namespace)

    test_namespace = {}
    try:
        exec(compile(test_code, 'test_code.py', 'exec'), test_namespace)
        test_class = test_namespace['Test']
    except Exception as e:  # noqa: BLE001
        result['error'] = 'Internal grading error (bad test definition): {0}'.format(e)
        write_results(secret_filename, result)
        return

    method_names = sorted(m for m in dir(test_class) if m.startswith('test_') and callable(getattr(test_class, m)))

    with contextlib.redirect_stdout(captured):
        test_results = [run_test_method(test_class, m, namespace) for m in method_names]

    _accumulate(result, test_results)
    result['student_output'] = captured.getvalue()
    write_results(secret_filename, result)


def _exec_setup_and_student(setup_code, student_code, target_ns, captured):
    with contextlib.redirect_stdout(captured):
        exec(compile(setup_code, 'setup_code.py', 'exec'), target_ns)
        exec(compile(student_code, 'student_code.py', 'exec'), target_ns)


def _evaluate_predict_call(predict_call, target_ns):
    """None if there's no prediction quiz on this question at all. Otherwise
    one of:
      {"kind": "function"} — the call displayed something callable; showing
        its repr (a memory address) isn't meaningful to a student.
      {"kind": "value", "repr": ...} — anything else, shown/matched as-is.
      {"kind": "error", "traceback": ...} — the call itself raised. Unlike a
        value mismatch (which hides the answer to make the student trace
        through it), a real error is a bug worth just showing them outright.

    `predict_call` can be several lines (server/services/predict_examples.py
    accumulates a docstring's prior lines, e.g. a `t = Tree(...)` setup
    before `tree_sum(t)`, since real doctest examples share one running
    session — likewise `a = hailstone(10)` before a later `b = hailstone(1)`
    in the same docstring needs `a`/`hailstone` still bound). All but the
    last line run for their side effects only, with their own output
    discarded — otherwise replaying an earlier example's prints would leak
    into and contaminate *this* example's captured output. Only the last
    line's output is what gets compared. It runs via `compile(...,
    'single')` — the same mode the real REPL/doctest use — so a bare
    expression's value is displayed via sys.displayhook exactly like typing
    it at a prompt would, and a statement that prints internally (the
    common "predict what prints" style, e.g. `a = hailstone(10)`) is
    captured the same way: as stdout, not a return value.
    """
    if predict_call is None:
        return None
    lines = [line for line in predict_call.splitlines() if line.strip()]
    if not lines:
        return None

    try:
        with contextlib.redirect_stdout(io.StringIO()):
            for line in lines[:-1]:
                exec(compile(line, 'predict_call', 'single'), target_ns)  # noqa: S102 - trusted, see module docstring

        displayed = []
        original_displayhook = sys.displayhook

        def _capture_displayhook(value):
            if value is not None:
                displayed.append(value)
            original_displayhook(value)

        captured = io.StringIO()
        try:
            sys.displayhook = _capture_displayhook
            with contextlib.redirect_stdout(captured):
                exec(compile(lines[-1], 'predict_call', 'single'), target_ns)  # noqa: S102
        finally:
            sys.displayhook = original_displayhook
    except Exception:  # noqa: BLE001 - untrusted code
        return {'kind': 'error', 'traceback': traceback.format_exc()}

    if displayed and callable(displayed[-1]):
        return {'kind': 'function'}
    output = captured.getvalue().rstrip('\n')
    return {'kind': 'value', 'repr': output if output else 'None'}


def _predict_result_for_exec_failure():
    """The student's code didn't even load — the prediction call couldn't
    possibly run, so it gets the same traceback as the main grading error
    rather than being silently left out of the response.
    """
    return {'kind': 'error', 'traceback': traceback.format_exc()}


def _accumulate(result, test_results):
    for test_result in test_results:
        result['test_results'].append(test_result)
        result['total_count'] += 1
        if test_result['passed']:
            result['passed_count'] += 1


def run_test_method(test_class, method_name, student_namespace):
    test_class.st = SimpleNamespace(**student_namespace)
    method = getattr(test_class, method_name)
    label = getattr(method, '_pl_name', method_name)
    instance = test_class(method_name)

    try:
        instance.setUp()
        getattr(instance, method_name)()
        message = '; '.join(instance._messages) if instance._messages else None
        passed = instance._score >= 1.0
    except AssertionError as e:
        message = str(e) or 'assertion failed'
        passed = False
    except Exception as e:  # noqa: BLE001 - untrusted code can raise anything
        message = '{0}: {1}'.format(type(e).__name__, e)
        passed = False

    return {
        'name': label,
        'passed': passed,
        'message': message,
    }


def write_results(secret_filename, result):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = os.path.join(RESULTS_DIR, secret_filename)
    with open(path, 'w') as f:
        json.dump(result, f)
    # Emit on stdout too — the parent process (run.sh, then Flask) reads
    # results this way rather than via a shared bind-mounted directory, which
    # avoids host/container UID-matching headaches for a throwaway container.
    print(json.dumps(result))


if __name__ == '__main__':
    main()
