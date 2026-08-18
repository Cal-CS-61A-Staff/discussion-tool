import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Polls `fetchFn(signal)` on an interval and exposes the latest result.
 * Skips a tick if the previous one is still in flight, pauses while the tab
 * is hidden, and aborts in-flight requests on unmount/param change.
 */
export function usePolling(fetchFn, { intervalMs = 2500, enabled = true } = {}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const inFlight = useRef(false);

  const tick = useCallback(
    async (signal) => {
      if (inFlight.current) return;
      inFlight.current = true;
      try {
        const result = await fetchFn(signal);
        setData(result);
        setError(null);
        setLoading(false);
      } catch (err) {
        // An aborted request (StrictMode's dev-mode double-effect-invoke
        // cancels the first mount's in-flight request, or a real param
        // change does) is not a completed tick — leave `loading` alone so
        // callers don't see a data=null/error=null/loading=false state
        // that neither of their guard clauses catches.
        if (err.name !== 'AbortError') {
          setError(err);
          setLoading(false);
        }
      } finally {
        inFlight.current = false;
      }
    },
    [fetchFn]
  );

  useEffect(() => {
    if (!enabled) return undefined;

    let cancelled = false;
    let timer = null;
    const controller = new AbortController();

    const schedule = () => {
      if (cancelled) return;
      timer = setTimeout(run, intervalMs);
    };

    async function run() {
      if (cancelled) return;
      if (!document.hidden) {
        await tick(controller.signal);
      }
      schedule();
    }

    run();

    const onVisibility = () => {
      if (!document.hidden) {
        clearTimeout(timer);
        run();
      }
    };
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      cancelled = true;
      controller.abort();
      clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [enabled, intervalMs, tick]);

  const refetch = useCallback(() => tick(), [tick]);

  return { data, error, loading, refetch };
}
