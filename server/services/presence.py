"""Presence — who's currently active in a group, i.e. has polled /state
within the staleness window (Config.TYPIST_STALE_SECONDS).

A GroupMembership row is permanent (roster/history/join-idempotency — see
server/blueprints/sections.py), but being *counted* toward the group for
anything live is presence-based, not permanent: typist assignment
(services/typist.py) and the ratings gate for advancing
(services/advance.py) both only care about who's actually here right now.
That's deliberate — a member who crashed/left and isn't coming back
shouldn't be able to block the group forever just by having once joined.

Every lookup here falls back to the full roster if literally nobody is
currently active, so a brief simultaneous gap in polling (everyone's
mid-navigation, a shared network blip) doesn't make the group's own gates
briefly impossible to satisfy.
"""

from datetime import timedelta

from server.config import Config
from server.models.group import GroupMembership
from server.utils import utcnow


def _stale_cutoff():
    return utcnow() - timedelta(seconds=Config.TYPIST_STALE_SECONDS)


def all_members(group_id, exclude_user_id=None):
    query = GroupMembership.query.filter_by(group_id=group_id)
    if exclude_user_id is not None:
        query = query.filter(GroupMembership.user_id != exclude_user_id)
    return query.all()


def active_members(group_id, exclude_user_id=None):
    query = GroupMembership.query.filter(
        GroupMembership.group_id == group_id,
        GroupMembership.last_seen_at >= _stale_cutoff(),
    )
    if exclude_user_id is not None:
        query = query.filter(GroupMembership.user_id != exclude_user_id)
    return query.all()


def active_or_all_members(group_id, exclude_user_id=None):
    return active_members(group_id, exclude_user_id) or all_members(group_id, exclude_user_id)


def active_member_count(group_id):
    return len(active_or_all_members(group_id))
