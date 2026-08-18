"""Doctest grading mode: runs the >>> examples already present in the
student's own function docstrings (the real CS61A/OkPy style) rather than a
separate PLTestCase test file. One test-result entry per >>> example.
"""

import doctest


class _RecordingDocTestRunner(doctest.DocTestRunner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []

    def report_success(self, out, test, example, got):
        self.records.append({'name': example.source.strip(), 'passed': True, 'message': None})

    def report_failure(self, out, test, example, got):
        message = 'expected {0!r}, got {1!r}'.format(example.want.strip(), got.strip())
        self.records.append({'name': example.source.strip(), 'passed': False, 'message': message})

    def report_unexpected_exception(self, out, test, example, exc_info):
        message = 'raised {0}: {1}'.format(exc_info[0].__name__, exc_info[1])
        self.records.append({'name': example.source.strip(), 'passed': False, 'message': message})


def run_doctests(module):
    """Runs every >>> example found in `module`'s docstrings.

    Returns a list of {name, points, max_points, passed, message} dicts, one
    per example, matching the shape runner.py's pltest path produces.
    """
    finder = doctest.DocTestFinder()
    tests = finder.find(module, module.__name__, module=module)
    runner = _RecordingDocTestRunner(optionflags=doctest.NORMALIZE_WHITESPACE)

    for test in tests:
        if test.examples:
            runner.run(test)

    return [
        {
            'name': record['name'][:80],
            'points': 1.0 if record['passed'] else 0.0,
            'max_points': 1,
            'passed': record['passed'],
            'message': record['message'],
        }
        for record in runner.records
    ]
