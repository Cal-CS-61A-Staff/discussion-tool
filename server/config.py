import os

SERVER_DIR = os.path.abspath(os.path.dirname(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SERVER_DIR, os.pardir))
INSTANCE_DIR = os.path.join(SERVER_DIR, "instance")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(INSTANCE_DIR, 'app.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_SAMESITE = "Lax"
    # Neon (our Postgres host) drops idle server-side connections well
    # under any reasonable pool_recycle default — a gunicorn worker that's
    # sat idle for a few minutes gets "SSL connection has been closed
    # unexpectedly" on its first query back, which SQLAlchemy surfaces as a
    # 500 instead of quietly reconnecting. pool_pre_ping does a cheap
    # SELECT 1 before handing out a pooled connection and transparently
    # replaces it if that fails; pool_recycle proactively retires
    # connections before Neon's own idle timeout gets to them so pre_ping
    # rarely even has to catch a dead one.
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}

    # Group-wide cooldown after a run attempt, in seconds.
    COOLDOWN_SECONDS = 30
    # A typist who hasn't polled /state in this long can be pre-empted by another member.
    TYPIST_STALE_SECONDS = 45
    # No progress on the current question for this long => "stuck" on the TA dashboard.
    STUCK_THRESHOLD_SECONDS = 360
    MAX_GROUP_SIZE = 4

    # Students are anonymous and everything they touch is transient. The
    # retention job (server/services/retention.py, run daily via
    # deploy/systemd/cs61a-retention.timer) snapshots participation to a
    # CSV under RETENTION_SNAPSHOT_DIR, then hard-deletes any group idle
    # (no poll or mutation) longer than this many days.
    SESSION_DATA_TTL_DAYS = int(os.environ.get("SESSION_DATA_TTL_DAYS", "14"))
    RETENTION_SNAPSHOT_DIR = os.environ.get(
        "RETENTION_SNAPSHOT_DIR", os.path.join(REPO_ROOT, "var", "snapshots")
    )
    # Anonymous participant cookies should outlast a single browser session
    # so a student who closes the tab mid-discussion can resume.
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 3

    # Grading runs in the student's browser now (Pyodide — client/src/pyodide/),
    # so there's no Docker, no grading queue, and no server-side per-run rate
    # limit — "Run tests" costs the server nothing but a row insert. The
    # client keeps a small fixed debounce between runs.

    # Rate-limit storage for the /login limits below
    # (server/blueprints/auth.py). In-memory by default now that Redis is no
    # longer needed for grading; set RATELIMIT_STORAGE_URI to a Redis URL if
    # you run multiple gunicorn workers and want the limit shared across them.
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    # Real deployments never need to touch this — it's here so a load test
    # (deploy/loadtest/) can isolate what it's actually measuring: many
    # synthetic VUs logging in from one IP in a tight window will otherwise
    # hit /login's brute-force limit itself, which is a test-script artifact
    # (production doesn't even use /login — see ALLOW_PASSWORDLESS_LOGIN),
    # not a finding about real capacity.
    RATELIMIT_ENABLED = os.environ.get("RATELIMIT_ENABLED", "true").lower() != "false"

    # Error monitoring (server/app.py) — entirely opt-in. With SENTRY_DSN
    # unset (the default everywhere, including production), sentry_sdk.init
    # is simply never called and nothing changes.
    SENTRY_DSN = os.environ.get("SENTRY_DSN")
    SENTRY_TRACES_SAMPLE_RATE = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.0"))

    # Real identity: Google OAuth restricted to this email domain. Login (and
    # role) still resolve through find_user_by_email (server/services/roster_import.py)
    # so a roster-imported TA/enrolled student keeps their assigned role/section.
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
    ALLOWED_EMAIL_DOMAIN = os.environ.get("ALLOWED_EMAIL_DOMAIN", "berkeley.edu")
    # The old self-declared name/role stub — kept for local dev without Google
    # credentials configured, hard-disabled in production (see ProdConfig).
    ALLOW_PASSWORDLESS_LOGIN = True


class DevConfig(Config):
    DEBUG = True


class ProdConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"
    ALLOW_PASSWORDLESS_LOGIN = False


def validate_prod_config(app):
    """Fail fast on startup rather than silently running production on dev defaults."""
    if app.config["SECRET_KEY"] == "dev-secret-change-me":
        raise RuntimeError("Set the SECRET_KEY environment variable before running in production.")
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite:"):
        raise RuntimeError("Set DATABASE_URL to a Postgres connection string before running in production.")
    if not app.config["GOOGLE_CLIENT_ID"] or not app.config["GOOGLE_CLIENT_SECRET"]:
        raise RuntimeError("Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET before running in production.")
