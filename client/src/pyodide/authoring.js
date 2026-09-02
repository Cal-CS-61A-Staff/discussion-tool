/** TA-editor save-time checks that used to run in the server's Docker
 * grader (server/blueprints/admin.py:_validate_reference_solution +
 * _resolve_prediction_items). Grading is in-browser now, so the editor
 * runs these before it POSTs and blocks the save on failure.
 */
import { pyodideRunner } from './runner.js';

/** Python string literal for an arbitrary JS string — mirrors `{s!r}`
 * closely enough for the generated test code (repr always single-quotes
 * unless the string contains a single quote and no double quote). */
function pyRepr(s) {
  const str = String(s ?? '');
  const hasSingle = str.includes("'");
  const hasDouble = str.includes('"');
  const quote = hasSingle && !hasDouble ? '"' : "'";
  const body = str
    .replace(/\\/g, '\\\\')
    .replace(new RegExp(quote, 'g'), '\\' + quote)
    .replace(/\n/g, '\\n')
    .replace(/\r/g, '\\r')
    .replace(/\t/g, '\\t');
  return quote + body + quote;
}

/** Port of server/services/test_case_grading.py:generate_simple_test_code —
 * kept byte-for-byte compatible so the browser validates the same test
 * code the server will store. */
export function generateSimpleTestCode(testCases) {
  const lines = [
    'from pl_unit_test import PLTestCase',
    'from pl_helpers import name',
    'from code_feedback import Feedback',
    '',
    '',
    'class Test(PLTestCase):',
  ];
  testCases.forEach((c, i) => {
    const call = pyRepr(c.call);
    const expected = pyRepr(c.expected);
    lines.push(
      '',
      `    @name(${call})`,
      `    def test_${i}(self):`,
      '        try:',
      `            actual = str(eval(${call}, dict(vars(self.st))))`,
      '        except Exception as e:',
      "            actual = '{0}: {1}'.format(type(e).__name__, e)",
      `        if Feedback.check_scalar(${call}, ${expected}, actual):`,
      '            Feedback.set_score(1)',
      '        else:',
      '            Feedback.set_score(0)'
    );
  });
  return lines.join('\n') + '\n';
}

/** Runs `referenceSolution` against the question's tests in Pyodide.
 * Returns {} on success, or {error, failingCases?} on rejection — same
 * shape/messages as the old server check so the editor's failing-case
 * panel keeps working. */
export async function validateReferenceSolution({ gradingMode, setupCode, testCases, testCode, referenceSolution }) {
  const mode = gradingMode === 'pltest' || gradingMode === 'simple' ? 'pltest' : 'doctest';
  const resolvedTest =
    gradingMode === 'simple'
      ? generateSimpleTestCode(testCases || [])
      : gradingMode === 'pltest'
        ? testCode || ''
        : '';

  const res = await pyodideRunner.runGrader({
    setup: setupCode || '',
    student: referenceSolution || '',
    test: resolvedTest,
    mode,
  });

  if (res.error) return { error: `Reference solution failed to run: ${res.error}` };
  if (gradingMode === 'doctest' && res.total_count === 0) {
    return { error: "No doctest examples (>>> ...) were found in the starter code's docstrings." };
  }
  if (res.passed_count !== res.total_count) {
    return {
      error: "Your reference solution doesn't pass its own test cases.",
      failingCases: (res.test_results || []).filter((t) => !t.passed),
    };
  }
  return {};
}

/** For an output-mode prediction: run each authored call against the
 * question's own code (setup + reference solution + the prediction's own
 * extra setup) and capture the output as the verified `expected`. Returns
 * {items} or {error}. */
export async function resolvePredictionItems({ prediction, setupCode, referenceSolution }) {
  if (!prediction || prediction.mode !== 'output') return { items: null };

  const callsText = Array.isArray(prediction.calls) ? prediction.calls.join('\n') : prediction.calls || '';
  const calls = callsText
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean);

  const context = [setupCode || '', referenceSolution || '', prediction.setup || '']
    .filter((p) => p && p.trim())
    .join('\n\n');

  const items = [];
  for (const call of calls) {
    const r = await pyodideRunner.runCall({ context, call });
    if (r.kind === 'timeout') return { error: `“${call}” timed out when run against the question's code.` };
    if (r.kind === 'error') return { error: `“${call}” raised an error when run against the question's code.` };
    items.push({ code: call, expected: r.kind === 'value' ? r.repr : '' });
  }
  return { items };
}
