# CS61A Discussion Viewer

A live, collaborative discussion-section tool. A TA publishes an assignment and hands out its **share link**; students open it, type a name and a group number, and start working — no account, no class join code. Everyone who types the same number is in the same group, and each group's progress on each assignment is tracked independently.

Each assignment has a shared typist-only code editor plus a private per-student scratch editor, an optional prediction prompt with right/wrong feedback, an autograder that runs the student's code against real test cases **in the browser** (Pyodide — real CPython compiled to WebAssembly, in a Web Worker), per-student confidence ratings that gate advancing to the next question, and a live TA dashboard. Non-code question types (multiple choice, fill-in-the-blank, short answer, "find a counterexample", …) render their own widgets on the same flow.

Nothing a student does is permanent. Identity is a signed-cookie *participant key* — there is no `users` row for a student. Group work is snapshotted to a participation CSV and then hard-deleted a couple of weeks after a group goes idle (see "Retention" below). Students can download a self-contained, re-runnable HTML copy of their work at any time.

Stack: React (Vite) frontend, Flask/SQLAlchemy backend (SQLite locally, Postgres in production via `DATABASE_URL`), synced with short-interval polling — no WebSockets. Staff/admin auth is Google OAuth restricted to a configurable email domain (`berkeley.edu` by default) in production; locally a passwordless stub takes over when no Google credentials are set. Both go through one boundary in `server/auth.py`. Grading has no server component — the harness (`client/src/pyodide/harness.py`) is a port of the old container grader and runs entirely client-side; the server just records the `{passed, total}` the browser reports.

## Prerequisites

- Python 3.11+
- Node 20+

(No Docker, no Redis — grading is in-browser and there is no job queue.)

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
npm install          # `predev`/`prebuild` vendor Pyodide into client/public/pyodide/
cd ..

# root dev convenience script (optional, for `npm run dev`)
npm install
```

Seed the demo class and assignments (creates `server/instance/app.db`):

```bash
source server/.venv/bin/activate
FLASK_APP=server.app flask seed-db
```

This creates one demo class ("CS 61A") with a couple of assignments. Publish an assignment (as staff, or via `flask` — see below) to get its `/w/<share_code>` link; open that link in a normal browser tab to try the student side.

## Run

Two terminals, from the repo root:

```bash
# terminal 1 — backend
source server/.venv/bin/activate
FLASK_APP=server.app FLASK_DEBUG=1 flask run -p 5050

# terminal 2 — frontend
cd client && npm run dev
```

Or, with the backend venv activated, `npm run dev` from the repo root runs both.

Open the Vite dev URL (usually http://localhost:5173). API calls are proxied to Flask on port 5050 — not 5000, since macOS's AirPlay Receiver squats on that port. Pyodide is served from `client/public/pyodide/` at `/pyodide/*` in dev and by Flask's static catch-all in production.

## Roles

Two global roles in `server/models/user.py`: `student` (the default for every real account) and `admin` (the out-of-band super-user). Per-class staff standing lives on `ClassMembership` (`role='staff'`), granted by an existing staff member or an admin. **Students are not accounts** — they never sign in; opening a share link mints an anonymous participant cookie.

Bootstrap an admin:

```bash
FLASK_APP=server.app flask create-admin "Your Name"        # dev: prints an id for "Sign in as admin"
FLASK_APP=server.app flask create-admin "You" --email you@berkeley.edu   # prod: resolved on first Google sign-in
```

Admins create classes and assign staff; any staff member of a class can author its assignments, watch its live dashboard, and download its participation CSVs. A staff member can preview an assignment as a student by opening its share link — they get a stable `staff-<id>` participant key and their solo group is excluded from grade rollups.

## Retention

Students are anonymous and their data is short-lived. `server/services/retention.py`, run daily by `deploy/systemd/cs61a-retention.{service,timer}` (`flask retention-run`):

1. **Snapshots** participation for every `(class, worksheet)` with activity to `RETENTION_SNAPSHOT_DIR/<class>/<worksheet>.csv` — one row per (group, participant): joined/last-seen, questions passed, completed. TAs download the merged (live + snapshot) file at `GET /api/worksheets/<id>/participation.csv`, or the "Download participation CSV" button on the Grades page.
2. **Purges** every `Group` whose `last_activity_at` is older than `SESSION_DATA_TTL_DAYS` (default 14), with all of its child rows.

`Group.last_activity_at` is bumped on every `/state` poll and every mutation. Run `flask retention-run --snapshot-only` to snapshot without purging.

## Try it out

1. As an admin, create a class; as staff, create an assignment, add a question, and Publish it. Copy the student link from the assignment page.
2. Open the link in another browser / incognito window. Enter a name and a group number; claim the pen; edit the code; hit "Run tests" — the first run shows "Loading Python…" while Pyodide downloads (cached after that), then real per-test-case pass/fail.
3. Not the typist? Use the private scratch editor below the shared one — its own "Run tests", unaffected by the group cooldown.
4. Rate your confidence. Open a third window, same number, rate too — "Next question" unlocks once everyone present has rated (and the tests pass, and any prediction is answered).
5. "Download my copy" in the breadcrumb → a single `.html` file that re-runs your Python offline (needs the network once, to fetch Pyodide from a CDN).

## Tests

```bash
source server/.venv/bin/activate
pip install -r server/requirements-dev.txt
pytest server/tests
```

Covers the concurrency-sensitive paths (typist-claim / cooldown / advance races, all guarded `UPDATE … WHERE` at the DB level), the anonymous participant flow, retention (snapshot + purge), the non-code problem types, and the export.

The in-browser grading harness has its own check (loads `client/src/pyodide/harness.py` under Pyodide in Node against a fixture set):

```bash
cd client && npm run verify-harness
```

CI runs `pytest` + `npm run build` + `npm run verify-harness` (`.github/workflows/ci.yml`).

## The autograder (`client/src/pyodide/`)

Grading is a ~250-line pure-Python harness (`harness.py`) — Feedback / `PLTestCase` / a recording doctest runner — run under Pyodide in a Web Worker (`worker.js`), driven by a singleton on the main thread (`runner.js`). A per-call timeout terminates and respawns the worker, which also catches an infinite loop in student code.

Two modes, selected per-question (`Question.grading_mode`):
- **`doctest`** — runs the `>>>` examples already in the student's own function docstrings (the CS61A/OkPy style). No separate test file.
- **`pltest`** — a `class Test(PLTestCase)` in `Question.test_code`, with `@name` and `Feedback.check_scalar` / `check_list`. `grading_mode='simple'` generates that class from TA-authored `{call, expected}` pairs (`server/services/test_case_grading.py`).

The client computes `{passed_count, total_count, test_results}` and POSTs it; the server records it on a `TestRun` row as-is (`server/blueprints/groups.py`). This is **trusted** — fine for participation-graded discussion, not for real grades. `code_snapshot` is still stored, so a run could be re-graded server-side later if that ever changed.

The TA editor validates a new question's reference solution the same way, in the browser, before saving (`client/src/pyodide/authoring.js`), and resolves each output-prediction call against the question's code to capture the expected output.

## Authoring questions

Two ways in, both landing on the same `Question` model.

**In the app (staff)**: open an assignment → "+ Add question" → title / problem description / problem code / setup code, choose a problem type, and (for autograded coding questions) add `{call, expected}` test cases or hand-written test code plus a reference "passing solution". The reference solution runs against the tests in the browser before the save is allowed. An optional prediction prompt can be attached to any question.

**As markdown files (`content/`)**: worksheets can also be git-committed markdown. See `server/content/loader.py` and `content/worksheets/cs61a-practice/` for the layout — `@code <file>` pulls in a starter-code file, `@pytest` marks a question doctest-graded, and a `:::solution … :::` block is shown only on demand. `server/seed.py` loads these at seed time.

## Production build

Postgres-ready: `SQLALCHEMY_DATABASE_URI` reads `DATABASE_URL` (SQLite only when unset), and schema changes go through Alembic (`server/migrations/`).

Required env vars — see `.env.example`. `ProdConfig` fails fast at startup if any are missing or wrong:

- `SECRET_KEY` — long random string; not the dev default.
- `DATABASE_URL` — a Postgres URL. SQLite is rejected outright.
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — the passwordless stub is hard-disabled in production, so staff sign-in needs these.
- `FLASK_ENV=production` — selects `ProdConfig`, turns on `SESSION_COOKIE_SECURE`, forces `https`. Must run behind HTTPS.
- `ALLOWED_EMAIL_DOMAIN` — defaults to `berkeley.edu`.
- `SESSION_DATA_TTL_DAYS` / `RETENTION_SNAPSHOT_DIR` — retention (see above). Defaults are 14 days and `<repo>/var/snapshots`.

`GET /api/health` checks real DB connectivity and returns 200/503 — point an uptime monitor at it.

### Rate limiting

Only `/api/auth/login` and `/api/auth/admin-login` are rate-limited (`server/blueprints/auth.py`) — the app polls constantly and classrooms share NAT'd IPs, so a blanket per-IP limit would throttle legitimate traffic. Storage is in-memory by default (fine for one gunicorn worker); set `RATELIMIT_STORAGE_URI` to a Redis URL to share it across several. Both login endpoints 404 in production anyway (`ALLOW_PASSWORDLESS_LOGIN`).

### Setting up Google sign-in

1. In [Google Cloud Console](https://console.cloud.google.com/), create a project → **APIs & Services → OAuth consent screen** (**Internal** for a Workspace org you control, else **External** — the app also rejects any email not ending in `ALLOWED_EMAIL_DOMAIN`).
2. **Credentials → Create Credentials → OAuth client ID → Web application**.
3. Authorized redirect URI: `https://<your-domain>/api/auth/google/callback` (and `http://localhost:5050/api/auth/google/callback` for local testing against real Google — must hit Flask's port directly, not Vite's).
4. Copy the **Client ID** / **Client Secret** into the env vars.

With those unset (local default), the login page falls back to the passwordless stub and `/api/auth/google/*` 404s.

### Bringing up a fresh Postgres database

```bash
DATABASE_URL=postgresql://... FLASK_APP=server.app flask db upgrade
DATABASE_URL=postgresql://... FLASK_APP=server.app flask create-admin "You" --email you@berkeley.edu
```

Whenever a model changes, generate and commit a migration:

```bash
FLASK_APP=server.app flask db migrate -m "describe the change"
FLASK_APP=server.app flask db upgrade
```

### Process supervision (`deploy/`)

`deploy/systemd/` has units for a single-VM deployment (the web app can also run from `Dockerfile` on a managed platform):

- `cs61a-discussion-web.service` — gunicorn on `127.0.0.1:8080`. Sync workers are fine — nothing blocks on grading anymore.
- `cs61a-retention.service` + `.timer` — daily `flask retention-run` (snapshot participation, purge idle groups). One-time: `sudo systemctl enable --now cs61a-retention.timer`.
- `cs61a-postgres-backup.service` + `.timer` — only if self-managing Postgres (see "Backups").

Install on a fresh VM:

```bash
sudo useradd --system --home /opt/cs61a-discussion cs61a
sudo cp deploy/systemd/*.service deploy/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cs61a-discussion-web
sudo systemctl enable --now cs61a-retention.timer
```

Both `.service` files read `/opt/cs61a-discussion/.env` (see `.env.example`). Create that file on the host; it isn't committed.

### Deploying a change

Pushing to `main` runs CI only. `deploy/scripts/deploy.sh` does the actual deploy — pulls `main`, reinstalls backend deps, runs migrations, rebuilds the frontend (which re-vendors Pyodide), restarts the web app, reloads the retention timer, then checks `/api/health`:

```bash
sudo -u cs61a bash /opt/cs61a-discussion/deploy/scripts/deploy.sh
```

### Reverse proxy & TLS (`deploy/Caddyfile`)

gunicorn just listens on `127.0.0.1:8080`. `deploy/Caddyfile` puts [Caddy](https://caddyserver.com/) in front — replace `fake-domain.example.edu` with your domain and Caddy provisions/renews a Let's Encrypt cert automatically.

```bash
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl restart caddy
```

Point DNS at the VM before starting Caddy. `server/app.py` wraps the app in `ProxyFix` under `ProdConfig` so per-IP rate limits see the real client address, not Caddy's.

### Error monitoring

Opt-in via `SENTRY_DSN` (`server/app.py`), unset by default. `SENTRY_TRACES_SAMPLE_RATE` (default `0`) controls performance tracing separately.

### Backups

Only if self-managing Postgres (RDS / Supabase / Neon / Fly Postgres all back it up for you). `deploy/scripts/backup_postgres.sh` runs `pg_dump --format=custom` to `$BACKUP_DIR` and prunes past `$BACKUP_RETENTION_DAYS`; set `BACKUP_S3_BUCKET` (with the `aws` CLI) to copy off-host.

```bash
sudo cp deploy/systemd/cs61a-postgres-backup.service deploy/systemd/cs61a-postgres-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cs61a-postgres-backup.timer
```

Restore: `pg_restore --clean --if-exists --dbname="$DATABASE_URL" /path/to/backup.dump` (use a `pg_restore` at least as new as the server).

## Swapping in real auth later

`server/auth.py` is the boundary for **staff/admin**: `get_current_user()`, `login_required`, `role_required`, `admin_required`. Everything downstream only needs `session["user_id"]` set to a real `User.id`. `GET /api/auth/google/{login,callback}` implement this against Google; a different provider just means an equivalent pair of routes ending the same way.

**Students** go through `server/participant.py` instead — `session["participant"] = {key, name}`, no `users` row. `server/blueprints/w.py` mints it on join. There's nothing to swap here; anonymity is the design.
