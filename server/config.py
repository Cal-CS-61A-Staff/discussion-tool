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


class DevConfig(Config):
    DEBUG = True


class ProdConfig(Config):
    DEBUG = False
