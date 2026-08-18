# CS61A Discussion Viewer

A live, collaborative discussion-section tool. Navigation is Class → Assignment → Group: a TA's class holds many assignments over time, students click into a TA-preassigned group (or work individually — both always available, no join codes), and each group's progress on each assignment is tracked independently. Each assignment: a shared typist-only code editor plus a private per-student scratch editor, a randomly-chosen prediction quiz with real right/wrong feedback, a sandboxed autograder that actually runs submitted code against test cases, per-student confidence ratings that gate advancing to the next question, and a live TA dashboard per assignment. TAs author new assignments/questions via a guided form (problem description, code, test cases, and a reference solution that's sandbox-validated before saving).

Stack: React (Vite) frontend + Flask/SQLAlchemy/SQLite backend, synced via short-interval polling (no WebSockets). Auth is currently a stub (enter a display name + role, no password) behind a clean boundary (`server/auth.py`) so real Canvas/bCourses OAuth can replace it later without touching the rest of the app.

## Prerequisites

- Python 3.11+
- Node 20+
- Docker (for the autograder — `docker build -t discussion-grader:latest ./grader`, see below)

## Setup

```bash
# backend
cd server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..

# frontend
cd client
npm install
cd ..

# root dev convenience script (optional, for `npm run dev`)
npm install

# autograder image (required before "Run tests" will work)
docker build -t discussion-grader:latest ./grader
```

Seed the demo class + assignments (creates `server/instance/app.db`):

```bash
source server/.venv/bin/activate
FLASK_APP=server.app flask seed-db
```

This creates one demo class ("CS 61A" / "Disc 12") with two assignments — the hand-authored tree-tracing worksheet and a markdown-authored Hailstone practice assignment (see below) — plus four pre-created groups (1-4). Sign in as either role and click the class card; no join code needed.

## Run

Two terminals, both from the repo root:

```bash
# terminal 1 — backend
source server/.venv/bin/activate
FLASK_APP=server.app FLASK_DEBUG=1 flask run -p 5050

# terminal 2 — frontend
cd client && npm run dev
```

Or, with the backend venv already activated, run both from the repo root at once: `npm run dev`.

Open the Vite dev URL (usually http://localhost:5173). API calls are proxied to the Flask server on port 5050 (chosen instead of the more conventional 5000 because macOS's AirPlay Receiver squats on 5000 by default).

## Try it out

1. Sign in as a student, click the demo class, click an assignment, then click a group card to join it (or "Work individually").
2. Claim the pen, edit the code, type a prediction for the randomly-shown call, hit "Run tests" — see the prediction-quiz feedback (styled as a grader-feedback panel) alongside the real per-test-case pass/fail from the sandboxed autograder.
3. Not the typist? Use your own private scratch editor below the shared one — it has an independent "Run tests" button, unaffected by the group cooldown.
4. Rate your confidence. Open a second browser (or an incognito window), sign in as a different student, join the same group on the same assignment, and rate too — "Next question" only unlocks once everyone in the group has rated.
5. Sign in as a TA: click the class, then "Manage groups" to bulk-create/rename/delete groups, or open an assignment's "Live dashboard" to watch groups live (click into a group for its full detail view, or release a stuck typist's pen), or "+ Add question" to author a new question via the guided form — try a deliberately wrong "passing solution" first to see it get rejected with the specific failing test case.
6. The same group's progress on two different assignments in the class is tracked completely independently (separate typist, cooldown, current question).

## Tests

```bash
source server/.venv/bin/activate
pip install -r server/requirements-dev.txt
pytest server/tests
```

Covers the concurrency-sensitive parts of the app (typist-claim race, run cooldown race, advance/double-advance race — all enforced with guarded `UPDATE ... WHERE` statements at the database level, not trusted client state), and the autograder (`server/tests/test_grading.py`, run against the real Docker image, not mocked — correct/wrong/malicious/infinite-loop submissions, for both grading modes).

## The autograder (`grader/`)

Modeled on PrairieLearn's `grader-python` external grader: one ephemeral, network-isolated, resource-limited Docker container per submission (`server/services/grading.py`), with the same root→secret-result-filename→drop-to-unprivileged-user security dance PrairieLearn's own `run.sh` uses internally.

Two grading modes, selected per-question (`Question.grading_mode`):
- **`pltest`** — a `class Test(PLTestCase)` in `Question.test_code`, using `@points`/`@name` decorators and `Feedback.check_scalar`/`check_list`, matching PrairieLearn's real test-authoring API (see `grader/harness/`).
- **`doctest`** — runs the `>>>` examples already present in the student's own function docstrings (the real CS61A/OkPy style) via Python's `doctest` module; no separate test file needed.

This is the correct *foundation* for scale, not "thousands of concurrent students" by itself — that needs a job queue and a worker fleet in front of the same container-invocation logic, which is a separate infrastructure project.

## Authoring questions

Two ways to author content, both landing on the same `Question` model:

**In the app (TAs)**: open an assignment → "+ Add question" → fill in title/difficulty/problem description/problem code, add one or more `{call, expected}` test cases, and paste a reference "passing solution". The reference solution is run through the real sandboxed grader against the test cases *before* saving (`POST /api/worksheets/:id/questions` in `server/blueprints/admin.py`) — a wrong reference solution is rejected with the specific failing case, catching authoring typos before students ever see them. This is `grading_mode="simple"`: `server/services/test_case_grading.py` auto-generates the `PLTestCase` test code from the structured test cases, reusing the grader's existing pltest path rather than a new container-side mode.

**As markdown files (`content/`)**: worksheets can also be authored as git-committed markdown instead of the form. Layout:

```
content/worksheets/<worksheet-slug>/
├── manifest.json            # {slug, title, class_course_name, class_name, question_ids: [...], ...}
└── questions/<question-id>/
    ├── question.md          # frontmatter + body (see content/worksheets/cs61a-practice/ for a real example)
    └── <code file>           # referenced by `code:` in the frontmatter / `@code <file>` in the body
```

`question.md` frontmatter (`id`, `title`, `difficulty`, `code`) is followed by a `---` and then markdown prose. Two directives are recognized (removed from the rendered prompt, not shown to students): `@code <file>` pulls in the sibling starter-code file, and `@pytest <name>` marks the question as doctest-graded (`grading_mode="doctest"` — runs the `>>>` examples already in the student's docstring, no separate test-case authoring needed). A `:::solution ... :::` block is extracted separately and only shown to students on demand. `manifest.json`'s `class_course_name`/`class_name` declare which class the assignment belongs to — `server/seed.py` upserts the class first (so multiple assignments, git-authored or form-authored, can share one class), then the worksheet under it.

`server/content/loader.py` is today's content source for the markdown path (reads these directories at seed time via `server/seed.py`). Fetching this same content from an external repo automatically is a natural next step — the loader is the abstraction boundary for that, mirroring how `server/auth.py` is the boundary for swapping in real OAuth later: a future `load_worksheet_from_repo(url)` would slot in without changing anything downstream.

## Production build

Not wired to a deploy target yet. `Dockerfile` builds the React app and serves it from Flask via gunicorn — SQLite needs a mounted volume for persistence in any real deployment, which isn't solved here since this is local-dev-only for now.

## Swapping in real auth later

`server/auth.py` is the auth boundary: `get_current_user()`, `login_required`, and `role_required` are used by every route. Replacing the fake-login stub (`POST /api/auth/login` in `server/blueprints/auth.py`) with a real Canvas/bCourses OAuth flow — as long as it ends in `session["user_id"] = user.id` — is the only change needed; nothing downstream changes.
