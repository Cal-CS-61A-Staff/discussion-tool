"""Runs as the unprivileged `ag` user (see run.sh). Loads the setup code and
(for pltest mode) test code into memory, deletes both from disk (so student
code — which runs in this same process — can't read the test definitions off
disk once it's running), execs setup+student code, then grades via one of
two modes selected by the GRADING_MODE env var:

  pltest (default) — runs each test_* method of a `class Test(PLTestCase)`
  defined in test_code.py (see pl_unit_test.py, code_feedback.py).

  doctest — runs the >>> examples already present in the student's own
  function docstrings (see doctest_runner.py); test_code.py is unused.
"""

import contextlib
import io
import json
import os
import sys
import types
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from doctest_runner import run_doctests  # noqa: E402

WORK_DIR = '/grade/work'
RESULTS_DIR = '/grade/results'


def main():
    grading_mode = os.environ.get('GRADING_MODE', 'pltest')
    secret_filename = os.environ['PL_RESULT_FILENAME']
    result = {
        'test_results': [],
        'total_points': 0,
        'max_points': 0,
        'passed_count': 0,
        'total_count': 0,
        'error': None,
        'student_output': '',
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
            result['student_output'] = captured.getvalue()
            write_results(secret_filename, result)
            return

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
        result['student_output'] = captured.getvalue()
        write_results(secret_filename, result)
        return

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


def _accumulate(result, test_results):
    for test_result in test_results:
        result['test_results'].append(test_result)
        result['max_points'] += test_result['max_points']
        result['total_points'] += test_result['points']
        result['total_count'] += 1
        if test_result['passed']:
            result['passed_count'] += 1


def run_test_method(test_class, method_name, student_namespace):
    test_class.st = SimpleNamespace(**student_namespace)
    method = getattr(test_class, method_name)
    max_points = getattr(method, '_pl_points', 1)
    label = getattr(method, '_pl_name', method_name)
    instance = test_class(method_name)

    try:
        instance.setUp()
        getattr(instance, method_name)()
        earned = instance._score * max_points
        message = '; '.join(instance._messages) if instance._messages else None
        passed = instance._score >= 1.0
    except AssertionError as e:
        earned = 0.0
        message = str(e) or 'assertion failed'
        passed = False
    except Exception as e:  # noqa: BLE001 - untrusted code can raise anything
        earned = 0.0
        message = '{0}: {1}'.format(type(e).__name__, e)
        passed = False

    return {
        'name': label,
        'points': earned,
        'max_points': max_points,
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
