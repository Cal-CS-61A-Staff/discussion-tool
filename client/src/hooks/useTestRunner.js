import { useEffect, useRef, useState } from 'react';
import * as groupsApi from '../api/groups.js';

const POLL_INTERVAL_MS = 1000;
// Grading itself is fast, but a queued job can wait behind other submissions
// under load (server/services/grading_queue.py) — generous but not infinite.
const MAX_POLL_ATTEMPTS = 120;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** Drives a single "run tests" action (shared editor or scratch editor),
 * each usage gets its own independent results state, but the grader
 * cooldown is per-user (server-enforced in grader_cooldown_service) so both
 * the shared and scratch runners resync to the same `graderCooldown` value
 * from the latest /state poll, ticking locally between polls for a smooth
 * countdown rather than a chunky one that only updates every 2.5s.
 *
 * "Run tests" itself is async server-side (a Docker container runs out of
 * process — see server/services/grading_jobs.py) so this submits, then
 * polls GET .../run-tests/:id until the worker fills in a result.
 */
export function useTestRunner(groupId, worksheetId, source, graderCooldown) {
  const [results, setResults] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const [remainingSeconds, setRemainingSeconds] = useState(graderCooldown?.remaining_seconds || 0);
  const [cooldownSeconds, setCooldownSeconds] = useState(graderCooldown?.cooldown_seconds || 0);
  const mountedRef = useRef(true);
  useEffect(
    () => () => {
      mountedRef.current = false;
    },
    []
  );

  useEffect(() => {
    if (!graderCooldown) return;
    setCooldownSeconds(graderCooldown.cooldown_seconds);
    setRemainingSeconds(graderCooldown.remaining_seconds);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graderCooldown?.remaining_seconds, graderCooldown?.cooldown_seconds]);

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
      const { test_run_id } = await groupsApi.runTests(groupId, worksheetId, code, prediction, source);

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
