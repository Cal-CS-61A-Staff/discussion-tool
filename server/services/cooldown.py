"""Group-wide run cooldown (per assignment), enforced with a DB-level
compare-and-swap against the group's GroupAssignmentProgress row.

`try_acquire` is the same guarded-UPDATE pattern as typist claims: two
simultaneous Run clicks are serialized by the database itself, since the
losing request's WHERE clause fails against the row the winner just wrote.
"""

from datetime import timedelta

from sqlalchemy import or_, update

from server.config import Config
from server.extensions import db
from server.models.group import GroupAssignmentProgress
from server.utils import utcnow


def try_acquire(progress):
    """Attempt to start a new attempt, respecting the group-wide cooldown.

    Returns True if the slot was acquired, False if a cooldown is active.
    """
    now = utcnow()
    result = db.session.execute(
        update(GroupAssignmentProgress)
        .where(GroupAssignmentProgress.id == progress.id)
        .where(
            or_(
                GroupAssignmentProgress.last_attempt_at.is_(None),
                GroupAssignmentProgress.last_attempt_at <= now - timedelta(seconds=Config.COOLDOWN_SECONDS),
            )
        )
        .values(last_attempt_at=now)
    )
    db.session.commit()
    if result.rowcount > 0:
        progress.last_attempt_at = now
        return True
    db.session.refresh(progress)
    return False


def remaining_seconds(progress):
    if progress.last_attempt_at is None:
        return 0
    elapsed = (utcnow() - progress.last_attempt_at).total_seconds()
    return max(round(Config.COOLDOWN_SECONDS - elapsed), 0)


def is_active(progress):
    return remaining_seconds(progress) > 0
