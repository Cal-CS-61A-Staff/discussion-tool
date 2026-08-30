from flask import Blueprint, current_app, jsonify, redirect, request, session, url_for

from server.auth import get_current_user, login_required
from server.extensions import db, limiter, oauth
from server.models.user import User
from server.services.roster_import import find_ta_by_name, find_user_by_email

auth_bp = Blueprint("auth", __name__)


@auth_bp.get("/config")
def auth_config():
    return jsonify(
        google_enabled=current_app.config["GOOGLE_OAUTH_ENABLED"],
        passwordless_enabled=current_app.config["ALLOW_PASSWORDLESS_LOGIN"],
    )


@auth_bp.get("/google/login")
def google_login():
    if not current_app.config["GOOGLE_OAUTH_ENABLED"]:
        return jsonify(error="Google sign-in is not configured"), 404
    redirect_uri = url_for("auth.google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.get("/google/callback")
def google_callback():
    """Verified-identity login: matches/creates a User exactly like /login's
    email path below, so a roster-imported TA or enrolled student keeps their
    assigned role/section the first time they actually sign in with Google.
    """
    if not current_app.config["GOOGLE_OAUTH_ENABLED"]:
        return jsonify(error="Google sign-in is not configured"), 404

    token = oauth.google.authorize_access_token()
    claims = oauth.google.userinfo(token=token)
    email = (claims.get("email") or "").strip().lower()
    allowed_domain = current_app.config["ALLOWED_EMAIL_DOMAIN"]
    if not email or not claims.get("email_verified") or not email.endswith(f"@{allowed_domain}"):
        return redirect("/login?error=domain_not_allowed")

    user = find_user_by_email(email)
    display_name = claims.get("name") or email.split("@")[0]
    if user is None:
        user = User(display_name=display_name, role="student", email=email)
        db.session.add(user)
    else:
        user.display_name = display_name
    db.session.commit()

    session["user_id"] = user.id
    return redirect("/")


@auth_bp.post("/login")
@limiter.limit("20 per minute")
def login():
    """Fake-login stub: creates a new User for whatever name+role is given —
    except:

    - If `email` is given, it's matched (case/whitespace-insensitive)
      against any existing account first, regardless of role — this is how
      a roster-imported account (server/services/roster_import.py, which
      creates a placeholder display_name from the email alone) gets its
      real name filled in on first actual login, and how a section
      assignment or SectionEnrollment made against that email survives
      logins rather than landing on a fresh, disconnected user every time.
      This is also the natural on-ramp for real Google/Canvas OAuth later,
      which would supply a *verified* email here instead of a
      self-reported one.
    - Else, a `ta` login falls back to matching an existing TA by name
      (older roster shape with no emails at all — see
      server/services/roster_import.py:import_ta_roster).

    Students with no email, and anyone not found by either match, get
    today's behavior: a brand new, unassigned account.

    No password. Disabled outright in production (ALLOW_PASSWORDLESS_LOGIN) now
    that /google/login above provides real, verified identity.
    """
    if not current_app.config["ALLOW_PASSWORDLESS_LOGIN"]:
        return jsonify(error="Passwordless login is disabled"), 404

    data = request.get_json(silent=True) or {}
    display_name = (data.get("display_name") or "").strip()
    role = data.get("role")
    email = (data.get("email") or "").strip()

    if not display_name:
        return jsonify(error="display_name is required"), 400
    if role not in ("student", "ta"):
        return jsonify(error="role must be 'student' or 'ta'"), 400

    user = find_user_by_email(email) if email else None
    if user is None and role == "ta":
        user = find_ta_by_name(display_name)

    if user is None:
        user = User(display_name=display_name, role=role, email=email or None)
        db.session.add(user)
    else:
        user.display_name = display_name
        if email:
            user.email = email.lower()
    db.session.commit()

    session["user_id"] = user.id
    return jsonify(user=_serialize_user(user))


@auth_bp.post("/admin-login")
@limiter.limit("5 per minute")
def admin_login():
    """Signs in as a pre-existing admin account (created out of band via
    `flask create-admin <name>` — see server/app.py) instead of creating a
    new one. Unlike /login above, this never creates a user or accepts a
    role — it only ever authenticates an id that already carries the
    'admin' role, so admin access still can't be self-granted from a form.

    Disabled in production alongside /login: a bare numeric id with no
    password/token is only safe as a local-dev convenience — ids are small
    sequential integers, so this would otherwise be brute-forceable with no
    rate limit. In production, `flask create-admin --email you@...` plus
    /google/login above is the real path: find_user_by_email resolves the
    pre-created admin row on first real sign-in, same as any roster-imported
    TA.
    """
    if not current_app.config["ALLOW_PASSWORDLESS_LOGIN"]:
        return jsonify(error="admin-login is disabled; sign in with Google instead"), 404

    data = request.get_json(silent=True) or {}
    try:
        admin_id = int(data.get("admin_id"))
    except (TypeError, ValueError):
        return jsonify(error="admin_id is required"), 400

    user = User.query.get(admin_id)
    if user is None or user.role != "admin":
        return jsonify(error="no admin account with that id"), 404

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
