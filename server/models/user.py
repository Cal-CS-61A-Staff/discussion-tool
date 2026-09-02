from server.extensions import db
from server.utils import utcnow


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    display_name = db.Column(db.String(80), nullable=False)
    # Global role, now only two meaningful values:
    #   'student' — the default for every login; per-class standing (student
    #               vs staff) lives on ClassMembership (server/models/klass.py),
    #               not here, so someone can be staff of one class and a
    #               student of another.
    #   'admin'   — out-of-band super-user (seed data, `flask create-admin`,
    #               or POST /api/admins). Bypasses every per-class check.
    # The old 'ta' value is retired — it no longer grants anything; a
    # migration rewrites existing 'ta' rows to 'student'.
    role = db.Column(db.String(10), nullable=False)
    # Optional today (the login form doesn't require it) — but when given,
    # it's the identity key roster imports match against (see
    # server/services/roster_import.py) instead of always creating a fresh
    # user, and gates which section's groups a student may join (see
    # server/models/section.py:SectionEnrollment). The natural on-ramp to
    # real Google/Canvas OAuth later, which would populate this for real
    # instead of trusting whatever the client sends.
    email = db.Column(db.String(120), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    # Per-user rate limit for the autograder (server/services/grading.py) —
    # separate from the group-wide predict/run cooldown, since spinning up a
    # container is a heavier operation and scratch-editor runs are personal.
    last_grader_run_at = db.Column(db.DateTime, nullable=True)
    # Consecutive-tries counter behind the escalating cooldown
    # (server/services/grader_cooldown.py) — resets to 0 once the user's
    # been idle long enough that this no longer counts as the same streak.
    grader_run_streak = db.Column(db.Integer, default=0, nullable=False)
