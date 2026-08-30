"""Per-user autograder rate limit — same guarded-UPDATE CAS pattern as
services/cooldown.py, but keyed by user instead of group, since spinning up
a grading container is a heavier operation we rate-limit independently of
the group-wide predict/run cooldown, and scratch-editor runs are personal.

Escalating: each consecutive try (within GRADER_COOLDOWN_RESET_SECONDS of
the last one) steps the required wait up the GRADER_COOLDOWN_STEPS ladder,
capping at its last entry. Going quiet for longer than that reset window
counts as a fresh start back at the first step.
"""

from datetime import timedelta

from sqlalchemy import or_, update

from server.config import Config
from server.extensions import db
from server.models.user import User
from server.utils import utcnow

# Comfortably longer than the ladder's own cap, so a user who was genuinely
# waiting out a cooldown (never longer than the cap) is still "in" their
# streak, while a real break resets it.
GRADER_COOLDOWN_RESET_SECONDS = Config.GRADER_COOLDOWN_STEPS[-1] * 2


def _duration_for_streak(streak):
    step_index = min(streak // Config.GRADER_COOLDOWN_STEP_TRIES, len(Config.GRADER_COOLDOWN_STEPS) - 1)
    return Config.GRADER_COOLDOWN_STEPS[step_index]


def _streak_at(user, now):
    """The user's try-streak as of `now` — 0 if they've been idle long
    enough that this doesn't count as a continuation of the last one."""
    if user.last_grader_run_at is None:
        return 0
    if (now - user.last_grader_run_at).total_seconds() > GRADER_COOLDOWN_RESET_SECONDS:
        return 0
    return user.grader_run_streak


def cooldown_seconds_for(user):
    """The wait required for the user's *next* try, given their current
    streak — what `cooldown_seconds` reports to the frontend."""
    return _duration_for_streak(_streak_at(user, utcnow()))


def try_acquire(user):
    now = utcnow()
    streak = _streak_at(user, now)
    duration = _duration_for_streak(streak)
    result = db.session.execute(
        update(User)
        .where(User.id == user.id)
        .where(
            or_(
                User.last_grader_run_at.is_(None),
                User.last_grader_run_at <= now - timedelta(seconds=duration),
            )
        )
        .values(last_grader_run_at=now, grader_run_streak=streak + 1)
    )
    db.session.commit()
    if result.rowcount > 0:
        user.last_grader_run_at = now
        user.grader_run_streak = streak + 1
        return True
    db.session.refresh(user)
    return False


def remaining_seconds(user):
    if user.last_grader_run_at is None:
        return 0
    now = utcnow()
    duration = _duration_for_streak(_streak_at(user, now))
    elapsed = (now - user.last_grader_run_at).total_seconds()
    return max(round(duration - elapsed), 0)
