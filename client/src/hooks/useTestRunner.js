import { useCallback, useEffect, useRef, useState } from 'react';
import * as groupsApi from '../api/groups.js';
import { pyodideRunner } from '../pyodide/runner.js';

const DEBOUNCE_MS = 3000;

/** Drives a "Run tests" action. Grading runs in the browser (Pyodide —
 * client/src/pyodide/); the result is then POSTed to persist it on a
 * TestRun row (server trusts it). A fixed post-run debounce replaces the
 * old server-enforced grader cooldown. */
export function useTestRunner(groupId, worksheetId, source, question) {
  const [results, setResults] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const [pyLoading, setPyLoading] = useState(pyodideRunner.isLoading());
  const [cooling, setCooling] = useState(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    pyodideRunner.warm();
    const off = pyodideRunner.onLoadingChange((l) => mountedRef.current && setPyLoading(l));
    return () => {
      mountedRef.current = false;
      off();
    };
  }, []);

  const run = useCallback(
    async (code) => {
      setError('');
      setRunning(true);
      try {
        const res = await pyodideRunner.runGrader({
          setup: question?.setup_code || '',
          student: code,
          test: question?.test_code || '',
          mode: question?.grading_mode || 'doctest',
        });
        if (!mountedRef.current) return;
        setResults(res);
        await groupsApi.runTests(groupId, worksheetId, code, res, source);
      } catch (err) {
        if (mountedRef.current) setError(err.message || 'Run failed');
      } finally {
        if (mountedRef.current) {
          setRunning(false);
          setCooling(true);
          setTimeout(() => mountedRef.current && setCooling(false), DEBOUNCE_MS);
        }
      }
    },
    [groupId, worksheetId, source, question?.setup_code, question?.test_code, question?.grading_mode]
  );

  return { results, running, error, run, pyLoading, cooling };
}
