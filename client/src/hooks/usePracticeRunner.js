import { useEffect, useRef, useState } from 'react';
import * as groupsApi from '../api/groups.js';

const POLL_INTERVAL_MS = 1000;
const MAX_POLL_ATTEMPTS = 120;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** Drives a personal "re-run tests" action from the History page's "View
 * work" section (server/blueprints/groups.py: POST .../practice-run) —
 * same async submit-then-poll shape as useTestRunner, but no prediction
 * step, and it doesn't touch the group's real progress/completed state.
 */
export function usePracticeRunner(groupId, worksheetId, questionId) {
  const [results, setResults] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const mountedRef = useRef(true);
  useEffect(
    () => () => {
      mountedRef.current = false;
    },
    []
  );

  const run = async (code) => {
    setError('');
    setRunning(true);
    try {
      const { test_run_id } = await groupsApi.practiceRun(groupId, worksheetId, questionId, code);

      let data = null;
      for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS && mountedRef.current; attempt++) {
        const poll = await groupsApi.getTestRunResult(groupId, test_run_id);
        if (poll.status === 'done') {
          data = poll;
          break;
        }
        await sleep(POLL_INTERVAL_MS);
      }
      if (!mountedRef.current) return;
      if (data === null) {
        throw new Error('Grading is taking longer than expected — please try again in a bit.');
      }
      setResults(data);
    } catch (err) {
      if (err.status === 429) {
        setError(`Cooldown active — wait ${err.data?.remaining_seconds ?? 'a few'}s before running again.`);
      } else {
        setError(err.message);
      }
    } finally {
      setRunning(false);
    }
  };

  return { results, running, error, run };
}
