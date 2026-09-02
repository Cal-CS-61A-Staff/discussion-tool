import { useCallback, useEffect, useRef, useState } from 'react';
import * as groupsApi from '../api/groups.js';
import { pyodideRunner } from '../pyodide/runner.js';

const DEBOUNCE_MS = 3000;

/** Personal "re-run tests" from previous-question browsing / the History
 * page. Grades in the browser (Pyodide), then records the run via
 * .../practice-run without touching the group's real progress. */
export function usePracticeRunner(groupId, worksheetId, questionId, question) {
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
        await groupsApi.practiceRun(groupId, worksheetId, questionId, code, res);
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
    [groupId, worksheetId, questionId, question?.setup_code, question?.test_code, question?.grading_mode]
  );

  return { results, running, error, run, pyLoading, cooling };
}
