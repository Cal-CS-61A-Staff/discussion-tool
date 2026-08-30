// Load test for the two traffic patterns discussed when sizing this app for
// production: (1) many students just having the site open (steady polling —
// group state every ~2.5s, matching the real frontend), and (2) a burst of
// students all clicking "Run tests" close together (a live section start).
//
// Requires the demo seed data (`flask seed-db`) with class/section id 1 —
// each VU creates its own individual group via /work-individually, so VUs
// never contend with each other for a shared group.
//
// Usage (from repo root, backend + at least one `flask grading-worker`
// already running):
//
//   k6 run deploy/loadtest/discussion_load_test.js
//   k6 run -e STEADY_VUS=300 -e BURST_VUS=300 deploy/loadtest/discussion_load_test.js
//
// A BURST_VUS burst against a single grading worker doesn't fail — it
// queues and drains one job at a time (see README "Grading concurrency").
// That's the thing to watch: run-tests itself should stay fast (~ms) even
// while the poll loop for a *result* takes longer under a big burst, since
// accepting a submission and finishing grading it are now decoupled.

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend } from 'k6/metrics';

const BASE = `${__ENV.BASE_URL || 'http://127.0.0.1:5050'}/api`;
const SECTION_ID = __ENV.SECTION_ID || 1;
const WORKSHEET_ID = __ENV.WORKSHEET_ID || 1;

const gradingWaitTime = new Trend('grading_wait_time', true);

export const options = {
  scenarios: {
    steady_state: {
      executor: 'ramping-vus',
      exec: 'steadyState',
      startVUs: 0,
      stages: [
        { duration: '20s', target: Number(__ENV.STEADY_VUS || 50) },
        { duration: '40s', target: Number(__ENV.STEADY_VUS || 50) },
        { duration: '10s', target: 0 },
      ],
    },
    grading_burst: {
      executor: 'per-vu-iterations',
      exec: 'gradingBurst',
      vus: Number(__ENV.BURST_VUS || 30),
      iterations: 1,
      startTime: '15s', // overlaps with steady_state, like a real section start
      maxDuration: '5m',
    },
  },
  thresholds: {
    // The submit call itself must stay fast regardless of queue depth —
    // that's the entire point of moving Docker off the request path.
    'http_req_duration{endpoint:run_tests_submit}': ['p(95)<1000'],
    'http_req_duration{endpoint:state_poll}': ['p(95)<1000'],
  },
};

function login(name) {
  const res = http.post(
    `${BASE}/auth/login`,
    JSON.stringify({ display_name: name, role: 'student' }),
    { headers: { 'Content-Type': 'application/json' }, tags: { endpoint: 'login' } }
  );
  check(res, { 'login ok': (r) => r.status === 200 });
}

function joinIndividually() {
  const res = http.post(
    `${BASE}/sections/${SECTION_ID}/work-individually`,
    JSON.stringify({}),
    { headers: { 'Content-Type': 'application/json' }, tags: { endpoint: 'work_individually' } }
  );
  check(res, { 'work-individually ok': (r) => r.status === 200 });
  return res.json('group.id');
}

// Steady background load: the thing every logged-in student's browser does
// just by having the page open, no grading involved.
//
// ramping-vus re-invokes this function in a loop for the whole scenario
// duration — one call must represent (close to) an entire VU's session,
// not a quick few-poll burst, or a failed request with no sleep on the
// fast-fail path lets a VU spin unthrottled and self-DoS the test.
export function steadyState() {
  login(`LoadTest Steady VU${__VU}`);
  const groupId = joinIndividually();
  if (!groupId) {
    sleep(2.5);
    return;
  }

  // ~24 polls * 2.5s ≈ 60s, roughly the scenario's sustained-load window —
  // keeps each VU logged in and polling for close to the whole test instead
  // of repeatedly logging back in as a brand-new user every few seconds.
  for (let i = 0; i < 24; i++) {
    const res = http.get(`${BASE}/groups/${groupId}/state?worksheet_id=${WORKSHEET_ID}`, {
      tags: { endpoint: 'state_poll' },
    });
    check(res, { 'state ok': (r) => r.status === 200 });
    sleep(2.5);
  }
}

// The scenario we actually built the queue for: everyone hits "Run tests"
// at once. Submission should return immediately regardless of burst size;
// only the poll-for-a-result loop should show the queueing effect.
export function gradingBurst() {
  login(`LoadTest Burst VU${__VU}`);
  const groupId = joinIndividually();
  if (!groupId) return;

  const submitRes = http.post(
    `${BASE}/groups/${groupId}/run-tests`,
    JSON.stringify({
      worksheet_id: WORKSHEET_ID,
      code: 'def tree_sum(t):\n    return t.label + sum([tree_sum(b) for b in t.branches])\n',
      prediction: '6',
      source: 'shared',
    }),
    { headers: { 'Content-Type': 'application/json' }, tags: { endpoint: 'run_tests_submit' } }
  );
  check(submitRes, { 'run-tests accepted immediately': (r) => r.status === 202 });
  if (submitRes.status !== 202) return;

  const testRunId = submitRes.json('test_run_id');
  const start = Date.now();
  let finished = false;
  for (let i = 0; i < 120 && !finished; i++) {
    sleep(1);
    const poll = http.get(`${BASE}/groups/${groupId}/run-tests/${testRunId}`, {
      tags: { endpoint: 'run_tests_poll' },
    });
    if (poll.json('status') === 'done') {
      finished = true;
      gradingWaitTime.add(Date.now() - start);
    }
  }
  check(null, { 'grading finished within 2 minutes': () => finished });
}
