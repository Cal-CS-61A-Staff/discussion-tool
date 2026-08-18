import { useEffect, useState } from 'react';
import * as groupsApi from '../api/groups.js';

/** Drives a single "run tests" action (shared editor or scratch editor),
 * each usage gets its own independent results state, but the grader
 * cooldown is per-user (server-enforced in grader_cooldown_service) so both
 * the shared and scratch runners resync to the same `graderCooldown` value
 * from the latest /state poll, ticking locally between polls for a smooth
 * countdown rather than a chunky one that only updates every 2.5s.
 */
export function useTestRunner(groupId, worksheetId, source, graderCooldown) {
  const [results, setResults] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const [remainingSeconds, setRemainingSeconds] = useState(graderCooldown?.remaining_seconds || 0);
  const [cooldownSeconds, setCooldownSeconds] = useState(graderCooldown?.cooldown_seconds || 0);

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
      const data = await groupsApi.runTests(groupId, worksheetId, code, prediction, source);
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
