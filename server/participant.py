"""Anonymous student identity.

Students have no account and no `users` row. When someone opens an
assignment share link (server/blueprints/w.py) and joins a group, we mint
a random key into the Flask signed-session cookie:

    session["participant"] = {"key": "<uuid4 hex>", "name": "<display name>"}

Every student-facing route identifies the caller with `get_participant()`
instead of `server.auth.get_current_user()`. The key is opaque and lives
only in the cookie plus the ephemeral group rows it appears on
(`GroupMembership.participant_key`, `Rating.participant_key`, ...), all of
which the retention job purges. Nothing student-identifying is persisted
server-side.

Staff/admin still authenticate through `server.auth` (a real `users` row +
`session["user_id"]`). A logged-in staff member who enters the student
flow ("view as student") also gets a participant key here, derived from
their user id so it's stable across a session.
"""

import uuid
from functools import wraps

from flask import g, jsonify, session

MAX_NAME_LEN = 60


def get_participant():
    """{'key': str, 'name': str} from the signed session, or None."""
    if "participant" in g:
        return g.participant
    data = session.get("participant")
    if isinstance(data, dict) and data.get("key"):
        g.participant = {"key": data["key"], "name": data.get("name") or ""}
    else:
        g.participant = None
    return g.participant


def current_participant_key():
    p = get_participant()
    return p["key"] if p else None


def mint_participant(name, *, key=None):
    """Create (or rename) the caller's participant identity and store it in
    the session cookie. Returns the key."""
    clean = (name or "").strip()[:MAX_NAME_LEN] or "Anonymous"
    key = key or uuid.uuid4().hex
    session["participant"] = {"key": key, "name": clean}
    session.permanent = True
    g.pop("participant", None)
    return key


def ensure_participant_for_staff(user):
    """Give a logged-in staff member a participant identity for the student
    flow, keyed off their user id so it's consistent within the session."""
    existing = get_participant()
    if existing:
        return existing["key"]
    return mint_participant(user.display_name, key=f"staff-{user.id}")


def participant_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if get_participant() is None:
            return jsonify(error="join the group from its share link first"), 401
        return view(*args, **kwargs)

    return wrapped
