"""The auth abstraction boundary.

Every route in this app identifies the caller through `get_current_user()`,
which currently reads a `user_id` stashed in the session by the fake-login
endpoint (`blueprints/auth.py`). Swapping in real Canvas/bCourses OAuth later
means replacing that login endpoint with a token exchange that still ends in
`session["user_id"] = user.id` — nothing downstream of this module changes.
"""

from functools import wraps

from flask import g, jsonify, session

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
    """'admin' always satisfies any role_required(...) check below it in the
    hierarchy (today that's just "ta") — an admin can do everything a TA
    can, plus section-assignment management (see admin_required). Ownership
    of a *specific* section still needs the separate ta_owns_section check
    below; this decorator only gates by role.
    """

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = get_current_user()
            if user is None:
                return jsonify(error="authentication required"), 401
            if user.role != role and user.role != "admin":
                return jsonify(error=f"{role} role required"), 403
            return view(*args, **kwargs)

        return wrapped

    return decorator


def admin_required(view):
    """Unlike role_required("ta"), this does NOT let a plain TA through —
    used for admin-only actions like assigning a section's TA.
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


def ta_owns_section(user, section):
    """True if `user` can manage `section`'s content/groups/roster: an
    admin always can; a TA either for the one section they primarily own
    (Section.ta_user_id) or one they've been granted co-authority over
    (SectionCoTeacher) — see server/models/section.py. Every existing
    TA-scoped endpoint already calls this (directly or via
    require_section_access below), so a co-teacher automatically gets the
    exact same access as the primary TA everywhere, with no per-endpoint
    changes needed.
    """
    if user.role == "admin":
        return True
    if user.role != "ta":
        return False
    if section.ta_user_id == user.id:
        return True
    return SectionCoTeacher.query.filter_by(section_id=section.id, user_id=user.id).first() is not None


def require_section_access(user, section):
    """Returns a (response, status) tuple to short-circuit a view with, or
    None if `user` may manage `section`. Callers already behind
    role_required("ta") (so `user` is a TA or admin) still need this: it's
    the difference between "some TA" and "this section's TA".
    """
    if not ta_owns_section(user, section):
        return jsonify(error="you don't have access to this class"), 403
    return None


def ta_owns_class(user, klass):
    """True if `user` may manage `klass`'s assignments: an admin always
    can; a TA if they own or co-teach *any* Section under this Class — a
    class's assignments are shared across every section in it, so any TA
    on its staff (not just one specific section's TA) can coordinate on
    the shared content. See ta_owns_section above for the per-section
    check this is built on.
    """
    if user.role == "admin":
        return True
    if user.role != "ta":
        return False
    return any(ta_owns_section(user, section) for section in klass.sections)


def require_class_access(user, klass):
    """Returns a (response, status) tuple to short-circuit a view with, or
    None if `user` may manage `klass`'s assignments.
    """
    if not ta_owns_class(user, klass):
        return jsonify(error="you don't have access to this class"), 403
    return None
