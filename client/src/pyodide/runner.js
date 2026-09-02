/** Main-thread API over the Pyodide grading worker. One worker, one call
 * at a time (Python runs synchronously in there); calls are queued. A
 * per-call timeout is enforced here by terminating and respawning the
 * worker — that's also how an infinite loop in student code is caught. */

let worker = null;
let readyPromise = null;
let readyResolve = null;
let loading = true;
let nextId = 1;
const pending = new Map(); // id -> { settle }
let queue = Promise.resolve(); // serialize calls onto the single worker

const listeners = new Set();
const emit = () => listeners.forEach((fn) => fn(loading));

function freshReady() {
  loading = true;
  readyPromise = new Promise((r) => (readyResolve = r));
  emit();
}
freshReady();

function spawn() {
  worker = new Worker(new URL('./worker.js', import.meta.url), { type: 'module' });
  worker.onmessage = (e) => {
    const msg = e.data;
    if (msg.type === 'ready') {
      loading = false;
      readyResolve();
      emit();
      return;
    }
    const p = pending.get(msg.id);
    if (!p) return;
    pending.delete(msg.id);
    p.settle(msg.ok ? { value: msg.result } : { error: new Error(msg.error || 'grading failed') });
  };
  worker.onerror = (e) => {
    for (const p of pending.values()) p.settle({ error: new Error(e.message || 'worker crashed') });
    pending.clear();
  };
}

function ensure() {
  if (!worker) spawn();
}

function respawn() {
  if (worker) worker.terminate();
  worker = null;
  for (const p of pending.values()) p.settle({ error: new Error('worker restarted') });
  pending.clear();
  freshReady();
  spawn();
}

function call(op, args, timeoutMs) {
  const run = () =>
    new Promise((resolve, reject) => {
      ensure();
      const id = nextId++;
      let timer = null;
      const settle = ({ value, error }) => {
        if (timer) clearTimeout(timer);
        if (error) reject(error);
        else resolve(value);
      };
      pending.set(id, { settle });
      if (timeoutMs) {
        timer = setTimeout(() => {
          pending.delete(id);
          respawn();
          reject(new Error('__timeout__'));
        }, timeoutMs);
      }
      worker.postMessage({ id, op, args });
    });
  const p = queue.then(run, run);
  queue = p.catch(() => {});
  return p;
}

const EMPTY = { test_results: [], passed_count: 0, total_count: 0, student_output: '' };

export const pyodideRunner = {
  whenReady: () => readyPromise,
  isLoading: () => loading,
  onLoadingChange(fn) {
    listeners.add(fn);
    return () => listeners.delete(fn);
  },
  /** Start loading the interpreter now, so the first Run isn't a cold start. */
  warm() {
    ensure();
    return readyPromise;
  },
  async runGrader({ setup = '', student = '', test = '', mode = 'doctest', timeoutMs = 10000 }) {
    try {
      return await call('grade', [setup, student, test, mode], timeoutMs);
    } catch (err) {
      if (err.message === '__timeout__') {
        return { ...EMPTY, error: 'Timed out — the code may have an infinite loop.' };
      }
      return { ...EMPTY, error: err.message || 'Grading failed. Try again.' };
    }
  },
  async runCall({ context = '', call: expr = '', timeoutMs = 6000 }) {
    try {
      return await call('run_call', [context, expr], timeoutMs);
    } catch (err) {
      if (err.message === '__timeout__') return { kind: 'timeout' };
      return { kind: 'error', traceback: err.message || 'failed' };
    }
  },
  /** TA editor: run each authored call against the question's code and
   * capture its output. Returns [{code, expected}] or throws. */
  async resolvePredictionItems({ context = '', calls = [] }) {
    const items = [];
    for (const c of calls) {
      const r = await this.runCall({ context, call: c });
      if (r.kind === 'timeout') throw new Error(`“${c}” timed out`);
      if (r.kind === 'error') throw new Error(`“${c}” raised an error against the question's code`);
      items.push({ code: c, expected: r.kind === 'value' ? r.repr : '' });
    }
    return items;
  },
};
