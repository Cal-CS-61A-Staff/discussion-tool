"""The auth abstraction boundary.

Every route in this app identifies the caller through `get_current_user()`,
which currently reads a `user_id` stashed in the session by the fake-login
endpoint (`blueprints/auth.py`). Swapping in real Canvas/bCourses OAuth later
means replacing that login endpoint with a token exchange that still ends in
`session["user_id"] = user.id` — nothing downstream of this module changes.
"""

from functools import wraps

from flask import g, jsonify, session

from server.models.user import User


def get_current_user():
    if "user" in g:
        return g.user
    user_id = session.get("user_id")
    g.user = User.query.get(user_id) if user_id else None
    return g.user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if get_current_user() is None:
            return jsonify(error="authentication required"), 401
        return view(*args, **kwargs)

    return wrapped


def role_required(role):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = get_current_user()
            if user is None:
                return jsonify(error="authentication required"), 401
            if user.role != role:
                return jsonify(error=f"{role} role required"), 403
            return view(*args, **kwargs)

        return wrapped

    return decorator
