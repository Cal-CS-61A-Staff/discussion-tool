/* eslint-env worker */
/* Web Worker: loads Pyodide (self-hosted at /pyodide/) once, then runs the
 * grading harness for each message. The main thread (runner.js) enforces
 * per-call timeouts by terminate()-ing and respawning this worker, so
 * there's no timeout logic here. */
import harnessSrc from './harness.py?raw';

let pyodideReady = null;

async function getPyodide() {
  if (!pyodideReady) {
    pyodideReady = (async () => {
      const { loadPyodide } = await import(/* @vite-ignore */ '/pyodide/pyodide.mjs');
      const py = await loadPyodide({ indexURL: '/pyodide/' });
      await py.runPythonAsync(harnessSrc);
      return py;
    })();
  }
  return pyodideReady;
}

// Warm up as soon as the worker starts.
getPyodide().then(
  () => postMessage({ type: 'ready' }),
  (err) => postMessage({ type: 'ready', error: String(err) })
);

function toPlain(proxy) {
  if (proxy && typeof proxy.toJs === 'function') {
    const v = proxy.toJs({ dict_converter: Object.fromEntries });
    proxy.destroy();
    return v;
  }
  return proxy;
}

onmessage = async (e) => {
  const { id, op, args } = e.data;
  try {
    const py = await getPyodide();
    const fn = py.globals.get(op); // 'grade' | 'run_call'
    let out;
    try {
      out = toPlain(fn(...args));
    } finally {
      fn.destroy();
    }
    postMessage({ id, ok: true, result: out });
  } catch (err) {
    postMessage({ id, ok: false, error: err && err.message ? err.message : String(err) });
  }
};
