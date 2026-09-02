"""The auth abstraction boundary.

Every route in this app identifies the caller through `get_current_user()`,
which currently reads a `user_id` stashed in the session by the fake-login
endpoint (`blueprints/auth.py`). Swapping in real Canvas/bCourses OAuth later
means replacing that login endpoint with a token exchange that still ends in
`session["user_id"] = user.id` — nothing downstream of this module changes.

Authorization is **per class**: a user's standing (student vs staff) lives on
`ClassMembership` (server/models/klass.py), not on the global `User.role`
(which now only marks the out-of-band `admin` super-user). This is what lets
someone be staff of one class and a student of another.
"""

from functools import wraps

from flask import g, jsonify, session

from server.models.klass import ClassMembership
from server.models.section import SectionCoTeacher
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
    """Back-compat shim. The only global role left that gates anything is
    'admin' (use `admin_required` for that). 'ta' is retired — per-class
    staff standing is enforced by `require_class_access` /
    `require_section_access`, which every `@role_required("ta")` route
    already calls immediately after. So `role_required("ta")` now just
    means "authenticated"; kept so the ~two dozen call sites don't all
    need touching.
    """

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = get_current_user()
            if user is None:
                return jsonify(error="authentication required"), 401
            if role == "admin" and user.role != "admin":
                return jsonify(error="admin role required"), 403
            return view(*args, **kwargs)

        return wrapped

    return decorator


def admin_required(view):
    """The global super-user gate — genuinely admin-only actions (assigning
    a room's staff member, creating/archiving/deleting a class, TA-roster
    import).
    """

    @wraps(view)
    def wrapped(*args, **kwargs):
        user = get_current_user()
        if user is None:
            return jsonify(error="authentication required"), 401
        if user.role != "admin":
            return jsonify(error="admin role required"), 403
        return view(*args, **kwargs)

    return wrapped


def is_class_staff(user, klass):
    """True if `user` may manage `klass` — an admin always can, or a
    'staff' ClassMembership for this class."""
    if user is None:
        return False
    if user.role == "admin":
        return True
    return (
        ClassMembership.query.filter_by(user_id=user.id, class_id=klass.id, role="staff").first()
        is not None
    )


def ta_owns_section(user, section):
    """Kept as a name; now just "is `user` staff of this room's class".
    `Section` is a Room and no longer confers access on its own — the
    ClassMembership does. Also records who runs the room for watch-list
    seeding (server/blueprints/ta.py)."""
    return is_class_staff(user, section.klass)


def runs_room(user, section):
    """True if `user` is the room's primary TA or a co-teacher on it —
    used only to seed a TA's dashboard watch list from the room's
    `assigned_numbers`, not for access control."""
    if section.ta_user_id == user.id:
        return True
    return SectionCoTeacher.query.filter_by(section_id=section.id, user_id=user.id).first() is not None


def require_section_access(user, section):
    """(response, status) to short-circuit with, or None if `user` may
    manage `section`'s room settings."""
    if not is_class_staff(user, section.klass):
        return jsonify(error="you don't have access to this class"), 403
    return None


def ta_owns_class(user, klass):
    """Kept as a name; alias of is_class_staff."""
    return is_class_staff(user, klass)


def require_class_access(user, klass):
    """(response, status) to short-circuit with, or None if `user` may
    manage `klass`'s assignments / dashboard / rooms (i.e. is staff)."""
    if not is_class_staff(user, klass):
        return jsonify(error="you don't have access to this class"), 403
    return None


