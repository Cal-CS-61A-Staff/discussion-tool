"""The per-user autograder cooldown (server/services/grader_cooldown.py)
escalates with consecutive tries instead of staying a flat wait — these
cover the ladder, the cap, and the idle-reset rule, since none of that is
exercised by the route-level tests in test_concurrency.py.
"""

from datetime import timedelta

from sqlalchemy import update

from server.config import Config
from server.extensions import db
from server.models.user import User
from server.services import grader_cooldown
from server.utils import utcnow


def _make_user(last_grader_run_at=None, grader_run_streak=0):
    user = User(display_name="s", role="student")
    db.session.add(user)
    db.session.commit()
    db.session.execute(
        update(User)
        .where(User.id == user.id)
        .values(last_grader_run_at=last_grader_run_at, grader_run_streak=grader_run_streak)
    )
    db.session.commit()
    db.session.refresh(user)
    return user


def test_first_try_uses_the_base_cooldown(app):
    user = _make_user()

    assert grader_cooldown.cooldown_seconds_for(user) == Config.GRADER_COOLDOWN_STEPS[0]
    assert grader_cooldown.try_acquire(user) is True
    assert user.grader_run_streak == 1
    # Immediately after acquiring, still one try into the streak — same step.
    assert grader_cooldown.cooldown_seconds_for(user) == Config.GRADER_COOLDOWN_STEPS[0]


def test_blocks_until_the_current_step_elapses(app):
    step_tries = Config.GRADER_COOLDOWN_STEP_TRIES
    step_duration = Config.GRADER_COOLDOWN_STEPS[1]
    user = _make_user(last_grader_run_at=utcnow() - timedelta(seconds=step_duration - 5), grader_run_streak=step_tries)

    assert grader_cooldown.cooldown_seconds_for(user) == step_duration
    assert grader_cooldown.try_acquire(user) is False
    assert grader_cooldown.remaining_seconds(user) > 0


def test_escalates_after_enough_tries(app):
    step_tries = Config.GRADER_COOLDOWN_STEP_TRIES
    user = _make_user(last_grader_run_at=utcnow() - timedelta(seconds=Config.GRADER_COOLDOWN_STEPS[1] + 1), grader_run_streak=step_tries)

    assert grader_cooldown.cooldown_seconds_for(user) == Config.GRADER_COOLDOWN_STEPS[1]
    assert grader_cooldown.try_acquire(user) is True
    assert user.grader_run_streak == step_tries + 1


def test_caps_at_the_last_step(app):
    huge_streak = Config.GRADER_COOLDOWN_STEP_TRIES * (len(Config.GRADER_COOLDOWN_STEPS) + 5)
    user = _make_user(last_grader_run_at=utcnow() - timedelta(seconds=Config.GRADER_COOLDOWN_STEPS[-1] + 1), grader_run_streak=huge_streak)

    assert grader_cooldown.cooldown_seconds_for(user) == Config.GRADER_COOLDOWN_STEPS[-1]
    assert grader_cooldown.try_acquire(user) is True


def test_long_idle_resets_the_streak(app):
    from server.services.grader_cooldown import GRADER_COOLDOWN_RESET_SECONDS

    user = _make_user(
        last_grader_run_at=utcnow() - timedelta(seconds=GRADER_COOLDOWN_RESET_SECONDS + 1),
        grader_run_streak=Config.GRADER_COOLDOWN_STEP_TRIES * 3,
    )

    assert grader_cooldown.cooldown_seconds_for(user) == Config.GRADER_COOLDOWN_STEPS[0]
    assert grader_cooldown.try_acquire(user) is True
    # Treated as a fresh start, not a continuation of the old streak.
    assert user.grader_run_streak == 1
