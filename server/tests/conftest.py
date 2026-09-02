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
    g.pop("user", None)
