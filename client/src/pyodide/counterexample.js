/** Client-side grading for 'counterexample' questions — a port of the
 * deleted server/services/counterexample_grading.py. The student supplies
 * input literals; we run the TA's buggy code and their hidden reference
 * with those inputs (Pyodide) and decide whether the student found a case
 * where the two disagree, or where the buggy one loops forever / raises
 * while the reference doesn't.
 *
 * Returns {isCorrect: boolean} on a graded verdict, or {error: string}
 * when the submission should be rejected (bad input, constraint not met,
 * or the reference itself won't run) rather than marked wrong.
 */
import { pyodideRunner } from './runner.js';

function normalizeOutput(text) {
  const lines = String(text ?? '')
    .split('\n')
    .map((l) => l.trim());
  while (lines.length && !lines[0]) lines.shift();
  while (lines.length && !lines[lines.length - 1]) lines.pop();
  return lines.join('\n');
}

export async function gradeCounterexample({ content, values }) {
  const params = (content?.params || []).map((p) => p.name);
  const setup = content?.setup || '';
  const callExpr = content?.call || '';

  // 1. Validate each input is a plain literal and resolve it to its Python
  //    repr (ast.literal_eval, same guard the server used).
  const reprs = {};
  for (const name of params) {
    const raw = (values || {})[name];
    if (raw == null || String(raw).trim() === '') {
      return { error: `enter a value for '${name}'` };
    }
    const r = await pyodideRunner.runCall({
      context: 'import ast',
      call: `ast.literal_eval(${JSON.stringify(String(raw))})`,
    });
    if (r.kind !== 'value') {
      return { error: `input '${name}' must be a plain number, string, tuple, or list` };
    }
    reprs[name] = r.repr;
  }

  const bindings = params.map((n) => `${n} = ${reprs[n]}`).join('\n');

  // 2. Optional TA-authored constraint over the inputs. A broken
  //    constraint expression shouldn't block the student, so only an
  //    explicit False rejects.
  const constraints = (content?.constraints || '').trim();
  if (constraints) {
    const r = await pyodideRunner.runCall({ context: bindings, call: `bool(${constraints})` });
    if (r.kind === 'value' && r.repr === 'False') {
      return { error: "those inputs don't satisfy the stated constraints" };
    }
  }

  // 3. Run buggy vs reference with those inputs.
  const predictCall = `${bindings}\n${callExpr}`;
  const buggy = await pyodideRunner.runCall({
    context: `${setup}\n\n${content?.buggy_code || ''}`,
    call: predictCall,
  });
  const reference = await pyodideRunner.runCall({
    context: `${setup}\n\n${content?.reference_code || ''}`,
    call: predictCall,
  });

  if (buggy.kind === 'timeout') return { isCorrect: true }; // loops forever on these inputs
  if (reference.kind === 'timeout' || reference.kind === 'error') {
    return { error: "couldn't run the reference solution — tell your TA" };
  }
  if (buggy.kind === 'error') return { isCorrect: true }; // buggy raises where the correct one doesn't

  if (buggy.kind === 'value' && reference.kind === 'value') {
    return { isCorrect: normalizeOutput(buggy.repr) !== normalizeOutput(reference.repr) };
  }
  // one displayed a bare function, the other a value — they disagree iff kinds differ
  return { isCorrect: buggy.kind !== reference.kind };
}
