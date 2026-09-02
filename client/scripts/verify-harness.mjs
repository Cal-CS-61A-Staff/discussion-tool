/** Smoke test for src/pyodide/harness.py — loads it under Pyodide in node
 * and runs grade()/run_call() against a small fixture set ported from the
 * old server/tests/test_grading.py. Run: `node scripts/verify-harness.mjs`.
 *
 * Not wired into CI (no JS test runner in this repo yet); it's a manual
 * check that the harness port still behaves after edits.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { loadPyodide } from '../node_modules/pyodide/pyodide.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const harnessSrc = readFileSync(join(here, '../src/pyodide/harness.py'), 'utf8');

let failed = 0;
function check(label, cond) {
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${label}`);
  if (!cond) failed++;
}

const py = await loadPyodide({ indexURL: join(here, '../node_modules/pyodide/') });
await py.runPythonAsync(harnessSrc);
const grade = py.globals.get('grade');
const runCall = py.globals.get('run_call');
const toJs = (p) => {
  const v = p.toJs({ dict_converter: Object.fromEntries });
  p.destroy();
  return v;
};

// --- doctest mode ------------------------------------------------------
const doctestStudent = `
def double(x):
    """
    >>> double(2)
    4
    >>> double(-3)
    -6
    """
    return x * 2
`;
let r = toJs(grade('', doctestStudent, '', 'doctest'));
check('doctest: all pass', r.passed_count === 2 && r.total_count === 2 && !r.error);

const doctestFail = `
def double(x):
    """
    >>> double(2)
    5
    """
    return x * 2
`;
r = toJs(grade('', doctestFail, '', 'doctest'));
check('doctest: a wrong want fails', r.passed_count === 0 && r.total_count === 1);

r = toJs(grade('', 'def f(x):\n    return x\n', '', 'doctest'));
check('doctest: no examples -> total 0', r.total_count === 0 && !r.error);

r = toJs(grade('', 'def broken(:\n', '', 'doctest'));
check('doctest: syntax error surfaces as error', Boolean(r.error) && r.total_count === 0);

// --- pltest mode -----------------------------------------------------
const pltestTest = `
from pl_unit_test import PLTestCase
from pl_helpers import name
from code_feedback import Feedback

class Test(PLTestCase):
    @name("adds")
    def test_adds(self):
        Feedback.set_score(1 if self.st.add(2, 3) == 5 else 0)
`;
r = toJs(grade('', 'def add(a, b):\n    return a + b\n', pltestTest, 'pltest'));
check('pltest: passing solution', r.passed_count === 1 && r.total_count === 1);
r = toJs(grade('', 'def add(a, b):\n    return a - b\n', pltestTest, 'pltest'));
check('pltest: wrong solution fails', r.passed_count === 0 && r.total_count === 1);

// --- run_call (prediction / counterexample) -------------------------
r = toJs(runCall('def fizz(n):\n    return n * 2\n', 'fizz(5)'));
check('run_call: value repr', r.kind === 'value' && r.repr === '10');
r = toJs(runCall('', 'print("hi")'));
check('run_call: printed output', r.kind === 'value' && r.repr === 'hi');
r = toJs(runCall('', '1 / 0'));
check('run_call: error kind', r.kind === 'error' && /ZeroDivisionError/.test(r.traceback));
r = toJs(runCall('def g():\n    pass\n', 'g'));
check('run_call: bare function', r.kind === 'function');

grade.destroy();
runCall.destroy();
console.log(failed ? `\n${failed} check(s) failed` : '\nall checks passed');
process.exit(failed ? 1 : 0);
