# CS61A Discussion Viewer

A live, collaborative discussion-section tool. Navigation is Class → Assignment → Group: a TA's class holds many assignments over time, students click into a TA-preassigned group (or work individually — both always available, no join codes), and each group's progress on each assignment is tracked independently. Each assignment: a shared typist-only code editor plus a private per-student scratch editor, a randomly-chosen prediction quiz with real right/wrong feedback, a sandboxed autograder that actually runs submitted code against test cases, per-student confidence ratings that gate advancing to the next question, and a live TA dashboard per assignment. TAs author new assignments/questions via a guided form (problem description, code, test cases, and a reference solution that's sandbox-validated before saving).

Stack: React (Vite) frontend + Flask/SQLAlchemy backend (SQLite locally, Postgres in production via `DATABASE_URL`), synced via short-interval polling (no WebSockets). Auth is Google OAuth restricted to a configurable email domain (`berkeley.edu` by default) in production; locally, a passwordless stub (enter a display name + role, no password) is used instead when Google credentials aren't configured — both sit behind a clean boundary (`server/auth.py`).

## Prerequisites

- Python 3.11+
- Node 20+
- Docker (for the autograder — `docker build -t discussion-grader:latest ./grader`, see below)
- Redis (grading jobs queue through it — `brew install redis && brew services start redis`, or `docker run -d -p 6379:6379 redis:7-alpine` if you'd rather not install it)

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

This creates one demo class ("CS 61A" / "Disc 12") with two assignments — the hand-authored tree-tracing worksheet and a markdown-authored Hailstone practice assignment (see below) — plus four pre-created groups (1-4). Sign in as a student and click the class card; no join code needed.

TAs, however, now only see classes they've been assigned to (see "Roles" below) — the seeded demo class starts unassigned, so a fresh TA login sees no classes at all until that one-time setup step is done.

## Run

Three terminals, all from the repo root:

```bash
# terminal 1 — backend
source server/.venv/bin/activate
FLASK_APP=server.app FLASK_DEBUG=1 flask run -p 5050

# terminal 2 — grading worker (runs the actual Docker container per "Run tests" click)
source server/.venv/bin/activate
FLASK_APP=server.app flask grading-worker

# terminal 3 — frontend
cd client && npm run dev
```

Or, with the backend venv already activated, run both from the repo root at once: `npm run dev`.

Open the Vite dev URL (usually http://localhost:5173). API calls are proxied to the Flask server on port 5050 (chosen instead of the more conventional 5000 because macOS's AirPlay Receiver squats on 5000 by default).

Without terminal 2 running (and Redis up), "Run tests" accepts the submission (it's enqueued) but never finishes grading it — see "Grading concurrency" below for why this is a separate process instead of Flask just calling Docker inline.

## Roles

Three roles: `student`, `ta`, `admin` (`server/models/user.py`). Student and TA are the same passwordless stub as always — pick a name and a role on the login screen, no verification. `admin` is different on purpose: it's never offered on that form, since it's meant to mimic how a real Canvas/bCourses "admin"/head-TA designation comes from the roster rather than something a user grants themselves. Instead:

```bash
FLASK_APP=server.app flask create-admin "Your Name"
```

prints the new admin's numeric id — use "Sign in as admin" on the login page with that id to authenticate as them locally (`POST /api/auth/admin-login`). This is a dev-only convenience and is disabled in production for the same reason the passwordless stub is (`ALLOW_PASSWORDLESS_LOGIN`) — a bare numeric id with no password would otherwise be brute-forceable. In production, pass `--email you@berkeley.edu` to `create-admin` and sign in with Google instead; `find_user_by_email` resolves the pre-created admin row on first real sign-in.

**TA scoping**: each class (`Section`) has at most one assigned TA (`Section.ta_user_id`) — a TA only sees and manages the one class they're assigned to (its groups, roster, assignments, live dashboard); every other class is invisible to them, same as a student's view. An admin sees and manages every class, and is the only role that can (re)assign a class's TA — from the "Admin" nav link, once signed in as an admin. Since every login is a fresh, non-persistent user (see "Swapping in real auth later" below), a TA needs to sign in at least once before an admin can find and assign them; if that TA later signs out and back in, they're a new user id and need reassigning.

**Discussion history**: both a group's own students and its TA/admin can see every released assignment that group has done in its class — status, progress, and points — via the "History" link next to a group's name (student worksheet page) or a group's row (TA's "Manage groups" page).

## Try it out

1. Sign in as a student, click the demo class, click an assignment, then click a group card to join it (or "Work individually").
2. Claim the pen, edit the code, type a prediction for the randomly-shown call, hit "Run tests" — see the prediction-quiz feedback (styled as a grader-feedback panel) alongside the real per-test-case pass/fail from the sandboxed autograder.
3. Not the typist? Use your own private scratch editor below the shared one — it has an independent "Run tests" button, unaffected by the group cooldown.
4. Rate your confidence. Open a second browser (or an incognito window), sign in as a different student, join the same group on the same assignment, and rate too — "Next question" only unlocks once everyone in the group has rated.
5. Sign in as a TA once (so that account exists), then bootstrap and sign in as an admin (see "Roles" above) and assign that TA to the demo class from the "Admin" page.
6. Sign back in as that TA: click the class, then "Manage groups" to bulk-create/rename/delete groups, or open an assignment's "Live dashboard" to watch groups live (click into a group for its full detail view, or release a stuck typist's pen), or "+ Add question" to author a new question via the guided form — try a deliberately wrong "passing solution" first to see it get rejected with the specific failing test case.
7. The same group's progress on two different assignments in the class is tracked completely independently (separate typist, cooldown, current question).

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

This is the correct *foundation* for scale, not "thousands of concurrent students" by itself — that needed a job queue and a worker fleet in front of the same container-invocation logic, which is what "Grading concurrency" below adds.

## Grading concurrency

Docker-per-submission is right for isolation, but a `docker run` blocking a Flask/gunicorn worker for the several seconds it takes is a real problem once more than a handful of students click "Run tests" close together (a burst at the start of a live section, say): every blocked worker is one fewer worker available to serve *any* request, grading-related or not — the whole site stalls, not just grading.

So `POST /groups/:id/run-tests` (`server/blueprints/groups.py`) no longer runs Docker itself. It validates the submission (membership, cooldown, etc.), creates a `TestRun` row with `status="pending"`, enqueues a job onto a Redis-backed queue (`server/services/grading_queue.py`), and returns immediately (202). The actual container invocation happens in a separate `flask grading-worker` process (`server/services/grading_jobs.py`) that pulls one job at a time off the queue, runs it through the exact same `grading.run_grader()` as before, and writes the result back onto the `TestRun` row. The frontend (`client/src/hooks/useTestRunner.js`) polls `GET /groups/:id/run-tests/:test_run_id` until `status: "done"`, then renders the result exactly as it did when the response was synchronous — the result shape didn't change, only *when* it arrives.

**Sizing the worker pool**: each `flask grading-worker` process handles one job — and therefore one Docker container — at a time, so the number of worker processes you run *is* your concurrent-grading cap. Each container is capped at `--cpus=0.5 --memory=128m` (`server/services/grading.py`), so N workers need roughly `0.5×N` CPU cores and `128MB×N` RAM available on whatever host runs them, on top of whatever the web app itself needs. Run as many as your hardware supports — e.g. `for i in $(seq 1 10); do FLASK_APP=server.app flask grading-worker & done` for 10 concurrent containers — under a real process supervisor in production (systemd template unit, supervisord, or your container platform's replica count), not loose background processes.

A burst larger than your worker count doesn't fail — it just queues. Submissions beyond the concurrent cap wait their turn (RQ's default queue behavior), so a spike of 300 students clicking "Run tests" at once degrades to "some students wait longer," not "the site goes down." The frontend's poll loop already tolerates several seconds of queueing.

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

Not wired to a deploy target yet, but the app is Postgres-ready: `SQLALCHEMY_DATABASE_URI` reads from the `DATABASE_URL` env var (falling back to local SQLite only when unset), and schema changes go through Alembic (`server/migrations/`) via Flask-Migrate instead of `db.create_all()`.

Required env vars in production (`ProdConfig` fails fast at startup if these aren't set correctly):
- `SECRET_KEY` — any long random string; must not be the dev default.
- `DATABASE_URL` — a Postgres URL, e.g. `postgresql://user:pass@host:5432/dbname`. SQLite is rejected outright.
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — from a Google OAuth client (see "Setting up Google sign-in" below). The passwordless dev stub is hard-disabled in `ProdConfig`, so these are required.
- `REDIS_URL` — e.g. `redis://host:6379/0`, backs the grading job queue (see "Grading concurrency" above). `ProdConfig` pings it at startup and refuses to boot if it's unreachable, since silently-broken grading is worse than a crash-on-deploy.
- `FLASK_ENV=production` — selects `ProdConfig` (see `server/app.py`), which also turns on `SESSION_COOKIE_SECURE` and forces the `https` URL scheme, so this must run behind HTTPS.
- `ALLOWED_EMAIL_DOMAIN` — defaults to `berkeley.edu`; only needed to launch for a different school/domain.
- `GRADER_IMAGE` — defaults to `discussion-grader:latest`; only needed if you tag it differently.

Also run one or more `flask grading-worker` processes (see "Grading concurrency" above) — the web process alone accepts submissions but never grades them.

`GET /api/health` checks real DB connectivity (not just "the process is up") and returns 200/503 — point a load balancer or uptime monitor at it.

### Rate limiting

Only `/api/auth/login` and `/api/auth/admin-login` are rate-limited (`server/extensions.py`, `server/blueprints/auth.py`) — deliberately not the whole app. This app polls constantly (group state every ~2.5s, run-tests every 1s while grading) and students are often behind one shared IP (campus WiFi/NAT), so a blanket per-IP limit would risk throttling a whole classroom's legitimate traffic instead of catching abuse. The two login endpoints are the exception because they're rare/one-shot *and* the only ones with brute-forceable auth (`admin-login` takes a bare numeric id — see "Roles" above) — `admin-login` is capped at 5/minute per IP, `login` at 20/minute. Both already 404 outright in production anyway (`ALLOW_PASSWORDLESS_LOGIN`), so this mainly matters for a staging environment that intentionally leaves passwordless login on. Backed by the same Redis as the grading queue (`RATELIMIT_STORAGE_URI`, defaults to `REDIS_URL`) so the limit holds across every gunicorn worker, not per-process.

### Setting up Google sign-in

1. In [Google Cloud Console](https://console.cloud.google.com/), create (or reuse) a project, then go to **APIs & Services → OAuth consent screen**. Choose **Internal** if this is a Google Workspace org you control (restricts to your org automatically) or **External** otherwise; either way, the app also independently rejects any email not ending in `ALLOWED_EMAIL_DOMAIN` server-side.
2. Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**, type **Web application**.
3. Add an **Authorized redirect URI** of `https://<your-domain>/api/auth/google/callback` (and, for local testing against real Google, `http://localhost:5050/api/auth/google/callback` — note this must hit Flask's own port directly, not the Vite dev port, since Google can't be proxied).
4. Copy the generated **Client ID** and **Client Secret** into the `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` env vars.

With those two env vars unset (the local dev default), the login page falls back to the passwordless stub and `/api/auth/google/*` routes 404 — nothing above is required to keep developing locally.

Bringing up a fresh Postgres database:

```bash
DATABASE_URL=postgresql://... FLASK_APP=server.app flask db upgrade
DATABASE_URL=postgresql://... FLASK_APP=server.app flask create-admin "Your Name" --email you@berkeley.edu
```

Whenever a model changes, generate and commit a new migration instead of hand-editing the schema:

```bash
FLASK_APP=server.app flask db migrate -m "describe the change"
FLASK_APP=server.app flask db upgrade
```

`Dockerfile` builds the React app and serves it from Flask via gunicorn. Remaining gaps before a real launch at meaningful scale:
- **Docker deployment**: `flask grading-worker` shells out to the `docker` CLI directly (`server/services/grading.py`), so it needs a host with real Docker daemon access — most fully-managed platforms (Heroku, Cloud Run, Fargate) don't allow this. Run it on a real VM (or a dedicated worker VM the web app doesn't share). See "Process supervision" below.
- **Backups**: only needed if you're self-managing Postgres — most managed hosts (RDS, Supabase, Neon, Fly Postgres) already do this for you. See "Backups" below if you are.

### Process supervision (`deploy/`)

Nothing should run as a loose background process in production — the web app, every grading worker, and the container reaper all need to come back on their own after a crash or reboot. `deploy/` has systemd units for a single-VM deployment (the web app can just as well run from `Dockerfile` on a managed platform instead — only the grading workers actually require a host with real Docker access):

- `cs61a-discussion-web.service` — gunicorn serving the app. Sync workers are fine here: "Run tests" no longer blocks on Docker (see "Grading concurrency" above), so nothing about serving pages or the frequent short polls needs the thread/async tuning that a synchronous Docker call would have required.
- `cs61a-grading-worker@.service` — a template unit; each instance is one `flask grading-worker` process, and therefore one concurrent Docker container (see "Grading concurrency" for sizing how many to run against real hardware).
- `cs61a-grader-reaper.service` + `.timer` — runs `deploy/scripts/reap_grader_containers.py` every 5 minutes, removing any `grader-*` container still around well past its own timeout — the crash-mid-grading case `grading.py`'s own `finally`-block cleanup can't catch, since that code only runs if the owning Python process is still alive.

To install on a fresh VM (adjust paths/user to taste):

```bash
sudo useradd --system --home /opt/cs61a-discussion cs61a
sudo usermod -aG docker cs61a   # lets the grading workers run `docker` without sudo

sudo cp deploy/systemd/*.service deploy/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload

sudo systemctl enable --now cs61a-discussion-web
sudo systemctl enable --now cs61a-grader-reaper.timer

# One instance per desired concurrent Docker container:
sudo systemctl enable --now cs61a-grading-worker@{1..10}
```

Both `.service` files read `/opt/cs61a-discussion/.env` for the env vars listed above (`SECRET_KEY`, `DATABASE_URL`, `GOOGLE_CLIENT_ID`/`SECRET`, `REDIS_URL`, etc.) — create that file on the host; it isn't (and shouldn't be) committed to the repo.

### Reverse proxy & TLS (`deploy/Caddyfile`)

Nothing terminates HTTPS on its own — gunicorn (`cs61a-discussion-web.service`) just listens on `127.0.0.1:8080`. `deploy/Caddyfile` puts [Caddy](https://caddyserver.com/) in front of it: replace `fake-domain.example.edu` with your real domain and Caddy provisions and renews a Let's Encrypt certificate automatically — no separate certbot setup. (nginx works too if you already run it elsewhere; Caddy's just less to configure correctly for one domain.)

```bash
sudo apt install -y caddy   # or your distro's equivalent
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl restart caddy
```

Point the domain's DNS A/AAAA record at the VM before starting Caddy, or it can't complete the Let's Encrypt challenge. `server/app.py` wraps the app in Werkzeug's `ProxyFix` whenever `ProdConfig` is active — without it, every request would appear to come from Caddy's own IP once behind the proxy, which would silently break the per-IP rate limits above (server/extensions.py) by bucketing every real user together under one address.

### Error monitoring

Opt-in via `SENTRY_DSN` (`server/app.py`) — unset by default everywhere, including production, so this is a "wire it up when you have an account" addition, not a required env var. Once set, uncaught exceptions in the web app, the CLI commands, and every `flask grading-worker` process (they all go through the same `create_app()`) get reported. `SENTRY_TRACES_SAMPLE_RATE` (default `0`) separately controls performance tracing, which costs quota — leave it off until you actually want it. Without a DSN, the app behaves exactly as it does today: exceptions go wherever gunicorn's own logs go, nothing more.

### Backups

Only relevant if you're self-managing Postgres rather than using a host that already backs it up (RDS, Supabase, Neon, Fly Postgres all do). `deploy/scripts/backup_postgres.sh` runs `pg_dump --format=custom` (compressed, restorable with `pg_restore`, including selective-table restores) to `$BACKUP_DIR` (default `/var/backups/cs61a-discussion`) and prunes anything older than `$BACKUP_RETENTION_DAYS` (default 14). Set `BACKUP_S3_BUCKET` (with the `aws` CLI available) to also copy each dump off-host — a backup that lives only on the same machine as the database doesn't protect against losing that machine outright. Requires `pg_dump`/`pg_restore` on the host (the `postgresql-client` package — a separate install from the app's own Python venv).

Install alongside the other systemd units (see "Process supervision" above):

```bash
sudo cp deploy/systemd/cs61a-postgres-backup.service deploy/systemd/cs61a-postgres-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cs61a-postgres-backup.timer
```

To restore: `pg_restore --clean --if-exists --dbname="$DATABASE_URL" /path/to/backup.dump`. Use a `pg_restore` version matching (or newer than) the *server's* major version — an older server can reject a directive a newer client's dump includes (e.g. `transaction_timeout`, added in Postgres 17), though as a session-level setting this specific one is safe to ignore if it comes up.

## Swapping in real auth later

`server/auth.py` is the auth boundary: `get_current_user()`, `login_required`, and `role_required` are used by every route — everything downstream only cares that `session["user_id"]` is set to a real `User.id`, not how it got there. `GET /api/auth/google/login` / `GET /api/auth/google/callback` in `server/blueprints/auth.py` implement this: they redirect to Google, verify the returned email is `email_verified` and ends in `ALLOWED_EMAIL_DOMAIN`, then resolve it through the same `find_user_by_email` used by roster import — so a TA or student who already exists (from `flask create-admin`, TA-roster import, or enrollment import) keeps their assigned role/section on first real sign-in, and anyone else gets a fresh `student` account. See "Setting up Google sign-in" above for the Cloud Console side. Swapping to a different provider (Canvas/bCourses OAuth, say) means writing an equivalent pair of routes that end the same way — nothing else changes.
