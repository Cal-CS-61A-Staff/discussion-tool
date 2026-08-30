from server.extensions import db
from server.utils import utcnow


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    display_name = db.Column(db.String(80), nullable=False)
    # 'student' | 'ta' | 'admin'. Unlike student/ta (self-selected at
    # login — see blueprints/auth.py), 'admin' is never offered on the
    # login form: it's granted out of band (seed data or a direct DB edit),
    # mirroring how a real Canvas/bCourses "admin" designation comes from
    # the roster/enrollment system rather than something a user picks.
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
