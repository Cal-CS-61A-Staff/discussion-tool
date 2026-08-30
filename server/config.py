import os

SERVER_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(SERVER_DIR, "instance")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(INSTANCE_DIR, 'app.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_SAMESITE = "Lax"

    # Group-wide cooldown after a run attempt, in seconds.
    COOLDOWN_SECONDS = 30
    # A typist who hasn't polled /state in this long can be pre-empted by another member.
    TYPIST_STALE_SECONDS = 45
    # No progress on the current question for this long => "stuck" on the TA dashboard.
    STUCK_THRESHOLD_SECONDS = 360
    MAX_GROUP_SIZE = 4

    # Per-user autograder rate limit (separate from COOLDOWN_SECONDS above,
    # which is group-wide and specific to the predict/run flow).
    GRADER_COOLDOWN_SECONDS = 10
    GRADER_IMAGE = os.environ.get("GRADER_IMAGE", "discussion-grader:latest")
    GRADER_CONTAINER_TIMEOUT_SECONDS = 15
    GRADER_DOCKER_CLI_TIMEOUT_SECONDS = 10

    # A "Run tests" click enqueues a grading job (server/services/grading_jobs.py)
    # onto this Redis-backed queue instead of running Docker inline on a web
    # worker — `flask grading-worker` runs the actual container per job. How
    # many concurrent Docker containers this allows is just how many worker
    # processes you run, not a value here (see README "Grading concurrency").
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    # Shared across gunicorn worker processes so the /login and /admin-login
    # limits below (server/blueprints/auth.py) actually hold under multiple
    # workers, not just per-process. Defaults to the same Redis as grading.
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", REDIS_URL)
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

    from redis import Redis
    from redis.exceptions import RedisError

    try:
        Redis.from_url(app.config["REDIS_URL"]).ping()
    except RedisError as e:
        raise RuntimeError(
            f"Could not reach Redis at REDIS_URL ({app.config['REDIS_URL']}) — grading jobs need it. {e}"
        )
