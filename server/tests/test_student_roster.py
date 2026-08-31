"""Covers the class-level student roster CSV import (columns Email, Name)
and the ClassEnrollment rows it produces — see
server/services/roster_import.py.
"""

from server.extensions import db
from server.models.klass import Class, ClassEnrollment
from server.models.user import User
from server.services.roster_import import find_user_by_email, import_student_roster, parse_student_roster
from server.tests.conftest import login_as

SAMPLE = (
    "Email,Name\n"
    "amy@berkeley.edu,Amy Adams\n"
    "ben@berkeley.edu,Ben Brown\n"
    "cara@berkeley.edu,\n"
    "\n"
)


def _class(db):
    klass = Class(course_name="CS 61A")
    db.session.add(klass)
    db.session.commit()
    return klass


def test_parse_student_roster_reads_email_and_optional_name():
    rows = parse_student_roster(SAMPLE)
    assert rows == [
        {"email": "amy@berkeley.edu", "name": "Amy Adams"},
        {"email": "ben@berkeley.edu", "name": "Ben Brown"},
        {"email": "cara@berkeley.edu", "name": ""},
    ]


def test_import_student_roster_creates_enrollments_and_named_placeholders(app, db):
    klass = _class(db)
    summary = import_student_roster(SAMPLE, klass.id)

    assert summary["enrollments_created"] == 3
    assert summary["students_created"] == 2  # cara has no name -> no placeholder

    emails = {e.student_email for e in ClassEnrollment.query.filter_by(class_id=klass.id).all()}
    assert emails == {"amy@berkeley.edu", "ben@berkeley.edu", "cara@berkeley.edu"}

    amy = find_user_by_email("amy@berkeley.edu")
    assert amy.role == "student" and amy.display_name == "Amy Adams"
    assert find_user_by_email("cara@berkeley.edu") is None


def test_import_student_roster_is_idempotent(app, db):
    klass = _class(db)
    import_student_roster(SAMPLE, klass.id)
    summary = import_student_roster(SAMPLE, klass.id)
    assert summary["enrollments_created"] == 0
    assert summary["enrollments_matched"] == 3
    assert summary["students_created"] == 0


def test_import_students_endpoint_requires_admin_and_class(app, client, db):
    klass = _class(db)
    admin = User(display_name="Admin", role="admin")
    ta = User(display_name="TA", role="ta")
    db.session.add_all([admin, ta])
    db.session.commit()

    login_as(client, ta)
    assert client.post("/api/roster/import-students", json={"csv": SAMPLE, "class_id": klass.id}).status_code == 403

    login_as(client, admin)
    assert client.post("/api/roster/import-students", json={"csv": SAMPLE}).status_code == 400
    resp = client.post("/api/roster/import-students", json={"csv": SAMPLE, "class_id": klass.id})
    assert resp.status_code == 200
    assert resp.get_json()["summary"]["enrollments_created"] == 3
