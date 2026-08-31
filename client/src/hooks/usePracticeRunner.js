import { useEffect, useRef, useState } from 'react';
import * as groupsApi from '../api/groups.js';

const POLL_INTERVAL_MS = 1000;
const MAX_POLL_ATTEMPTS = 120;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** Drives a personal "re-run tests" action from the shared Assignments
 * page / previous-question browsing (server/blueprints/groups.py: POST
 * .../practice-run) — same async submit-then-poll shape as useTestRunner,
 * including the same prediction quiz and the same live cooldown countdown
 * (same per-user grader_cooldown_service backing both), but it doesn't
 * touch the group's real progress/completed state.
 */
export function usePracticeRunner(groupId, worksheetId, questionId) {
  const [results, setResults] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const [remainingSeconds, setRemainingSeconds] = useState(0);
  const [cooldownSeconds, setCooldownSeconds] = useState(0);
  const mountedRef = useRef(true);
  useEffect(
    () => () => {
      mountedRef.current = false;
    },
    []
  );

  useEffect(() => {
    if (remainingSeconds <= 0) return undefined;
    const id = setInterval(() => setRemainingSeconds((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [remainingSeconds > 0]);

  const run = async (code, prediction) => {
    setError('');
    setRunning(true);
    try {
      const { test_run_id } = await groupsApi.practiceRun(groupId, worksheetId, questionId, code, prediction);

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
      if (typeof data.cooldown_seconds === 'number') {
        setCooldownSeconds(data.cooldown_seconds);
        setRemainingSeconds(data.cooldown_seconds);
      }
    } catch (err) {
      if (err.status === 429) {
        const remaining = err.data?.remaining_seconds;
        const total = err.data?.cooldown_seconds;
        setError(`Cooldown active — wait ${remaining ?? 'a few'}s before running again.`);
        if (typeof remaining === 'number') setRemainingSeconds(remaining);
        if (typeof total === 'number') setCooldownSeconds(total);
      } else {
        setError(err.message);
      }
    } finally {
      setRunning(false);
    }
  };

  return { results, running, error, run, remainingSeconds, cooldownSeconds };
}
