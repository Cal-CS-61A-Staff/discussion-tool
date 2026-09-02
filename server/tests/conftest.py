import pytest
from flask import g

from server.app import create_app
from server.config import Config
from server.extensions import db as _db


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    RATELIMIT_ENABLED = False  # no Redis in the test environment


@pytest.fixture()
def app():
    flask_app = create_app(TestConfig)
    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.drop_all()


@pytest.fixture()
def db(app):
    return _db


@pytest.fixture()
def client(app):
    return app.test_client()


def make_class(course_name="CS 61A", join_code="TESTAA"):
    """A Class with a join code (required now). Bump `join_code` if a test
    needs more than one class."""
    from server.models.klass import Class

    klass = Class(course_name=course_name, join_code=join_code)
    _db.session.add(klass)
    _db.session.flush()
    return klass


def add_member(user, klass, role="student"):
    """Give `user` a per-class role. 'staff' is what used to be a global
    `User(role="ta")` + section assignment."""
    from server.models.klass import ClassMembership

    _db.session.add(ClassMembership(user_id=user.id, class_id=klass.id, role=role))
    _db.session.flush()


def publish(worksheet):
    """Give a worksheet a share_code so the student flow can reach it."""
    from server.blueprints.admin import _ensure_share_code

    worksheet.is_published = True
    _ensure_share_code(worksheet)
    _db.session.flush()
    return worksheet.share_code


def join_worksheet(client, worksheet, name="Alex", number=1):
    """The anonymous student flow: resolve the share link and join a group
    by number. Returns the new group's id. Sets the test client's
    participant cookie."""
    code = worksheet.share_code or publish(worksheet)
    _db.session.commit()
    resp = client.post(f"/api/w/{code}/join", json={"name": name, "number": number})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["group_id"]


def set_participant(client, key="p-test", name="Tester"):
    """Directly stamp a participant identity onto the test client session,
    for tests that build group rows by hand. Clears any staff login so the
    two identities don't bleed together across a test."""
    with client.session_transaction() as sess:
        sess["participant"] = {"key": key, "name": name}
        sess.pop("user_id", None)
    g.pop("participant", None)
    g.pop("user", None)


def new_browser(client):
    """Simulate a completely fresh browser: drop the session cookie *and*
    the request-local identity cache. The `app` fixture keeps one app
    context pushed for the whole test, so `get_participant()` /
    `get_current_user()` would otherwise carry the previous request's
    resolved identity (cached on `g`) straight into the next request even
    after the cookie is cleared -- the same reason `login_as` pops `g`."""
    with client.session_transaction() as sess:
        sess.clear()
    g.pop("participant", None)
    g.pop("user", None)


def pkey(user):
    """The deterministic participant key a test uses for a stand-in User row
    (students have no real accounts anymore)."""
    return f"u{user.id}"


def act_as_participant(client, user):
    """Test shim: identify the client as the anonymous participant that
    stands in for `user` in a hand-built group."""
    set_participant(client, pkey(user), user.display_name)


def add_group_member(group, user):
    from server.models.group import GroupMembership

    _db.session.add(
        GroupMembership(group_id=group.id, participant_key=pkey(user), participant_name=user.display_name)
    )
    _db.session.flush()


def login_as(client, user):
    """Switches the test client's session to `user`. The `app` fixture keeps
    one app context pushed for the whole test (so a single client.get() can
    read the DB session outside a request too), but that means Flask's
    request-local `g` — where get_current_user() caches the resolved user —
    doesn't get a fresh app context per call the way it would in real HTTP
    serving. Clearing it here is what makes switching identities mid-test
    (e.g. TA publishes something, then a student's view is checked) actually
    take effect on the next request.
    """
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess.pop("participant", None)
    g.pop("user", None)
    g.pop("participant", None)
