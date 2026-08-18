from server.extensions import db
from server.utils import utcnow


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    display_name = db.Column(db.String(80), nullable=False)
    role = db.Column(db.String(10), nullable=False)  # 'student' | 'ta'
    created_at = db.Column(db.DateTime, default=utcnow)
    # Per-user rate limit for the autograder (server/services/grading.py) —
    # separate from the group-wide predict/run cooldown, since spinning up a
    # container is a heavier operation and scratch-editor runs are personal.
    last_grader_run_at = db.Column(db.DateTime, nullable=True)
