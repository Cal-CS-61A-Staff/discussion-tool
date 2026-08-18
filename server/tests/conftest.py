import pytest
from flask import g

from server.app import create_app
from server.config import Config
from server.extensions import db as _db


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


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
