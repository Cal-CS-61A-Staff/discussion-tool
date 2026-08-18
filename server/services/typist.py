"""Typist (pen) assignment.

Rather than students claiming the pen themselves, it's assigned at random
among a group's currently *active* members (anyone who has polled /state
within Config.TYPIST_STALE_SECONDS — the same recency window used
elsewhere in this app to judge staleness) whenever the group reaches a new
question, and reassigned at random — excluding whoever's giving it up —
whenever the current typist voluntarily gives it up or is found to have
gone inactive (closed the tab, lost connection, etc).

`give_up_typist` still uses the guarded `UPDATE ... WHERE` CAS pattern
(same as the rest of this app's group-state mutations) so it only succeeds
if the caller genuinely holds the pen at commit time. The other entry
points here are server-triggered rather than user-triggered, so a
plain read-then-write is fine — a rare double-reassignment race between two
members' concurrent polls is harmless (worst case the pen flips between two
random picks within milliseconds).
"""

import random
from datetime import timedelta

from sqlalchemy import update

from server.config import Config
from server.extensions import db
from server.models.group import GroupAssignmentProgress, GroupMembership
from server.utils import utcnow


def _active_members(group_id, exclude_user_id=None):
    cutoff = utcnow() - timedelta(seconds=Config.TYPIST_STALE_SECONDS)
    query = GroupMembership.query.filter(
        GroupMembership.group_id == group_id,
        GroupMembership.last_seen_at >= cutoff,
    )
    if exclude_user_id is not None:
        query = query.filter(GroupMembership.user_id != exclude_user_id)
    return query.all()


def _all_members(group_id, exclude_user_id=None):
    query = GroupMembership.query.filter_by(group_id=group_id)
    if exclude_user_id is not None:
        query = query.filter(GroupMembership.user_id != exclude_user_id)
    return query.all()


def assign_random_typist(progress, group_id, exclude_user_id=None):
    """Randomly assigns the pen among active members (falling back to
    every member if nobody's currently active, so the pen never sits
    empty just because everyone's mid-navigation). Returns the chosen
    user_id, or None if the group has nobody to assign to.
    """
    candidates = _active_members(group_id, exclude_user_id) or _all_members(group_id, exclude_user_id)
    if not candidates:
        progress.typist_user_id = None
        progress.typist_claimed_at = None
        db.session.commit()
        return None

    chosen = random.choice(candidates)
    progress.typist_user_id = chosen.user_id
    progress.typist_claimed_at = utcnow()
    db.session.commit()
    return chosen.user_id


def reassign_if_stale(progress, group_id):
    """Called on every /state poll: if the current typist has gone
    inactive (or there isn't one yet), hand the pen to someone else so a
    student closing the tab doesn't strand the group.
    """
    if progress.typist_user_id is None:
        assign_random_typist(progress, group_id)
        return

    cutoff = utcnow() - timedelta(seconds=Config.TYPIST_STALE_SECONDS)
    membership = GroupMembership.query.filter_by(group_id=group_id, user_id=progress.typist_user_id).first()
    if membership is not None and membership.last_seen_at >= cutoff:
        return

    assign_random_typist(progress, group_id)


def give_up_typist(progress, group_id, user_id):
    """The current typist voluntarily releases the pen; it goes to a
    random *other* active member. Returns False if `user_id` isn't
    actually the current typist (stale click / already handed off).
    """
    candidates = _active_members(group_id, exclude_user_id=user_id) or _all_members(group_id, exclude_user_id=user_id)
    new_typist_id = random.choice(candidates).user_id if candidates else user_id

    result = db.session.execute(
        update(GroupAssignmentProgress)
        .where(GroupAssignmentProgress.id == progress.id, GroupAssignmentProgress.typist_user_id == user_id)
        .values(typist_user_id=new_typist_id, typist_claimed_at=utcnow())
    )
    db.session.commit()
    if result.rowcount == 0:
        return False

    progress.typist_user_id = new_typist_id
    progress.typist_claimed_at = utcnow()
    return True


def release_typist(progress, group_id):
    """TA override: force a random reassignment regardless of who
    currently holds the pen or whether they've gone stale yet — a TA is
    trusted to make this call unconditionally.
    """
    assign_random_typist(progress, group_id)
