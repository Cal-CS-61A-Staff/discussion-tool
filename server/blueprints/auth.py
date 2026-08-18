from flask import Blueprint, jsonify, request, session

from server.auth import get_current_user, login_required
from server.extensions import db
from server.models.user import User

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/login")
def login():
    """Fake-login stub: creates a new User for whatever name+role is given.

    No password. See server/auth.py for how this is meant to be swapped
    out for real Canvas/bCourses OAuth later.
    """
    data = request.get_json(silent=True) or {}
    display_name = (data.get("display_name") or "").strip()
    role = data.get("role")

    if not display_name:
        return jsonify(error="display_name is required"), 400
    if role not in ("student", "ta"):
        return jsonify(error="role must be 'student' or 'ta'"), 400

    user = User(display_name=display_name, role=role)
    db.session.add(user)
    db.session.commit()

    session["user_id"] = user.id
    return jsonify(user=_serialize_user(user))


@auth_bp.get("/me")
@login_required
def me():
    return jsonify(user=_serialize_user(get_current_user()))


@auth_bp.post("/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


def _serialize_user(user):
    return {"id": user.id, "display_name": user.display_name, "role": user.role}
