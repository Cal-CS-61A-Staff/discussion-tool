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
from server.services import presence
from server.utils import utcnow


def assign_random_typist(progress, group_id, exclude_key=None):
    """Randomly assigns the pen among active members (falling back to
    every member if nobody's currently active, so the pen never sits
    empty just because everyone's mid-navigation). Returns the chosen
    participant key, or None if the group has nobody to assign to.
    """
    candidates = presence.active_or_all_members(group_id, exclude_key)
    if not candidates:
        progress.typist_key = None
        progress.typist_claimed_at = None
        db.session.commit()
        return None

    chosen = random.choice(candidates)
    progress.typist_key = chosen.participant_key
    progress.typist_claimed_at = utcnow()
    db.session.commit()
    return chosen.participant_key


def reassign_if_stale(progress, group_id):
    """Called on every /state poll: if the current typist has gone
    inactive (or there isn't one yet), hand the pen to someone else so a
    student closing the tab doesn't strand the group.
    """
    if progress.typist_key is None:
        assign_random_typist(progress, group_id)
        return

    cutoff = utcnow() - timedelta(seconds=Config.TYPIST_STALE_SECONDS)
    membership = GroupMembership.query.filter_by(group_id=group_id, participant_key=progress.typist_key).first()
    if membership is not None and membership.last_seen_at >= cutoff:
        return

    assign_random_typist(progress, group_id)


def give_up_typist(progress, group_id, participant_key):
    """The current typist voluntarily releases the pen; it goes to a
    random *other* active member. Returns False if `participant_key` isn't
    actually the current typist (stale click / already handed off).
    """
    candidates = presence.active_or_all_members(group_id, exclude_key=participant_key)
    new_typist_key = random.choice(candidates).participant_key if candidates else participant_key

    result = db.session.execute(
        update(GroupAssignmentProgress)
        .where(GroupAssignmentProgress.id == progress.id, GroupAssignmentProgress.typist_key == participant_key)
        .values(typist_key=new_typist_key, typist_claimed_at=utcnow())
    )
    db.session.commit()
    if result.rowcount == 0:
        return False

    progress.typist_key = new_typist_key
    progress.typist_claimed_at = utcnow()
    return True


def release_typist(progress, group_id):
    """TA override: force a random reassignment regardless of who
    currently holds the pen or whether they've gone stale yet — a TA is
    trusted to make this call unconditionally.
    """
    assign_random_typist(progress, group_id)


def leave(progress, group_id, participant_key):
    """Explicit "I'm navigating away" signal (StudentWorksheetPage gives
    this up on unmount for in-app navigation — not reliable for a closed
    tab/refresh, which still falls back to reassign_if_stale's timeout).
    Marks the participant inactive immediately instead of waiting out
    TYPIST_STALE_SECONDS of missed polls, and hands off the pen right away
    if they were the one holding it.
    """
    stale_at = utcnow() - timedelta(seconds=Config.TYPIST_STALE_SECONDS + 1)
    db.session.execute(
        update(GroupMembership)
        .where(GroupMembership.group_id == group_id, GroupMembership.participant_key == participant_key)
        .values(last_seen_at=stale_at)
    )
    db.session.commit()
    if progress.typist_key == participant_key:
        assign_random_typist(progress, group_id, exclude_key=participant_key)
