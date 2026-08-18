"""Per-user autograder rate limit — same guarded-UPDATE CAS pattern as
services/cooldown.py, but keyed by user instead of group, since spinning up
a grading container is a heavier operation we rate-limit independently of
the group-wide predict/run cooldown, and scratch-editor runs are personal.
"""

from datetime import timedelta

from sqlalchemy import or_, update

from server.config import Config
from server.extensions import db
from server.models.user import User
from server.utils import utcnow


def try_acquire(user):
    now = utcnow()
    result = db.session.execute(
        update(User)
        .where(User.id == user.id)
        .where(
            or_(
                User.last_grader_run_at.is_(None),
                User.last_grader_run_at <= now - timedelta(seconds=Config.GRADER_COOLDOWN_SECONDS),
            )
        )
        .values(last_grader_run_at=now)
    )
    db.session.commit()
    if result.rowcount > 0:
        user.last_grader_run_at = now
        return True
    db.session.refresh(user)
    return False


def remaining_seconds(user):
    if user.last_grader_run_at is None:
        return 0
    elapsed = (utcnow() - user.last_grader_run_at).total_seconds()
    return max(round(Config.GRADER_COOLDOWN_SECONDS - elapsed), 0)
