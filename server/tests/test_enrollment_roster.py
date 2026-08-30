"""Covers importing the per-student enrollment export (Student Email, Staff
Email, Location, Day, Start, Type), the email-based login persistence it
enables, and the join-time enrollment gate it turns on for sections that
actually have imported roster data. See server/services/roster_import.py.
"""

from server.extensions import db
from server.models.group import Group
from server.models.klass import Class
from server.models.section import Section, SectionEnrollment
from server.models.user import User
from server.services.roster_import import find_user_by_email, import_enrollment_roster, parse_enrollment_roster
from server.tests.conftest import login_as

SAMPLE_ENROLLMENT = (
    "Student Email\tStaff Email\tLocation\tDay\tStart\tType\n"
    "alice@berkeley.edu\tlavanya@berkeley.edu\tVLSB2038\tR\t2:00 PM\tDiscussion\n"
    "bob@berkeley.edu\tlavanya@berkeley.edu\tVLSB2038\tR\t2:00 PM\tDiscussion\n"
    "carol@berkeley.edu\tandrew@berkeley.edu\tVLSB2030\tR\t5:00 PM\tDiscussion\n"
    "alice@berkeley.edu\tstaff-lab@berkeley.edu\tCORY521\tR\t2:00 PM\tLab\n"
    "dave@berkeley.edu\t\tVLSB2038\tR\t2:00 PM\tOffice Hours\n"
)


def test_parse_enrollment_roster_keeps_only_discussion_rows():
    rows = parse_enrollment_roster(SAMPLE_ENROLLMENT)
    assert len(rows) == 3
    assert all(r["staff_email"] or r["student_email"] == "carol@berkeley.edu" for r in rows)
    emails = {r["student_email"] for r in rows}
    assert emails == {"alice@berkeley.edu", "bob@berkeley.edu", "carol@berkeley.edu"}


def test_import_enrollment_roster_creates_sections_tas_and_enrollments(app, db):
    summary = import_enrollment_roster(SAMPLE_ENROLLMENT)

    assert summary["sections_created"] == 2
    assert summary["tas_created"] == 2
    assert summary["enrollments_created"] == 3

    klass = Class.query.filter_by(course_name="CS 61A").first()
    assert klass is not None
    section = Section.query.filter_by(class_id=klass.id, name="R 2:00 PM (VLSB2038)").first()
    assert section is not None

    lavanya = find_user_by_email("lavanya@berkeley.edu")
    assert lavanya is not None
    assert lavanya.role == "ta"
    assert lavanya.display_name == "lavanya"  # placeholder from the email local-part
    assert section.ta_user_id == lavanya.id

    enrolled_emails = {
        e.student_email for e in SectionEnrollment.query.filter_by(section_id=section.id).all()
    }
    assert enrolled_emails == {"alice@berkeley.edu", "bob@berkeley.edu"}


def test_import_enrollment_roster_is_idempotent(app, db):
    import_enrollment_roster(SAMPLE_ENROLLMENT)
    summary = import_enrollment_roster(SAMPLE_ENROLLMENT)

    assert summary["sections_created"] == 0
    assert summary["sections_matched"] == 2
    assert summary["tas_created"] == 0
    assert summary["tas_matched"] == 2
    assert summary["enrollments_created"] == 0
    assert summary["enrollments_matched"] == 3


def test_login_with_email_fills_in_placeholder_name_and_persists(app, client, db):
    import_enrollment_roster(SAMPLE_ENROLLMENT)
    lavanya = find_user_by_email("lavanya@berkeley.edu")
    assert lavanya.display_name == "lavanya"

    resp = client.post(
        "/api/auth/login",
        json={"display_name": "Lavanya Shyamsundar", "role": "ta", "email": "Lavanya@Berkeley.edu"},
    )
    assert resp.status_code == 200
    body = resp.get_json()["user"]
    assert body["id"] == lavanya.id
    assert body["display_name"] == "Lavanya Shyamsundar"
    assert body["role"] == "ta"

    db.session.refresh(lavanya)
    assert lavanya.display_name == "Lavanya Shyamsundar"


def test_login_email_takes_priority_over_stored_role_not_requested_role(app, client, db):
    # A roster-matched account's role is authoritative -- logging in with a
    # different role selected in the form does not change it.
    import_enrollment_roster(SAMPLE_ENROLLMENT)
    resp = client.post(
        "/api/auth/login", json={"display_name": "Lavanya", "role": "student", "email": "lavanya@berkeley.edu"}
    )
    assert resp.get_json()["user"]["role"] == "ta"


def test_student_blocked_from_joining_section_they_are_not_enrolled_in(app, client, db):
    import_enrollment_roster(SAMPLE_ENROLLMENT)
    section = Section.query.filter_by(name="R 2:00 PM (VLSB2038)").first()
    db.session.add(Group(section_id=section.id, number=1, name="Group 1"))
    db.session.commit()

    login_resp = client.post(
        "/api/auth/login", json={"display_name": "Carol", "role": "student", "email": "carol@berkeley.edu"}
    )
    assert login_resp.status_code == 200

    resp = client.post(f"/api/sections/{section.id}/groups/join", json={"number": 1})
    assert resp.status_code == 403
    assert "not enrolled" in resp.get_json()["error"]


def test_student_can_join_section_they_are_enrolled_in(app, client, db):
    import_enrollment_roster(SAMPLE_ENROLLMENT)
    section = Section.query.filter_by(name="R 2:00 PM (VLSB2038)").first()
    db.session.add(Group(section_id=section.id, number=1, name="Group 1"))
    db.session.commit()

    client.post("/api/auth/login", json={"display_name": "Alice", "role": "student", "email": "alice@berkeley.edu"})
    resp = client.post(f"/api/sections/{section.id}/groups/join", json={"number": 1})
    assert resp.status_code == 200


def test_section_with_no_imported_roster_stays_open(app, client, db):
    klass = Class(course_name="C")
    db.session.add(klass)
    db.session.flush()
    section = Section(class_id=klass.id, name="Ungated Section")
    db.session.add(section)
    db.session.flush()
    db.session.add(Group(section_id=section.id, number=1, name="Group 1"))
    db.session.commit()

    client.post(
        "/api/auth/login", json={"display_name": "Nobody On Roster", "role": "student", "email": "nobody@x.com"}
    )
    resp = client.post(f"/api/sections/{section.id}/groups/join", json={"number": 1})
    assert resp.status_code == 200


def test_student_with_no_email_is_never_gated(app, client, db):
    import_enrollment_roster(SAMPLE_ENROLLMENT)
    section = Section.query.filter_by(name="R 2:00 PM (VLSB2038)").first()
    db.session.add(Group(section_id=section.id, number=1, name="Group 1"))
    db.session.commit()

    client.post("/api/auth/login", json={"display_name": "No Email Given", "role": "student"})
    resp = client.post(f"/api/sections/{section.id}/groups/join", json={"number": 1})
    assert resp.status_code == 200


def test_import_enrollment_endpoint_is_admin_only(app, client, db):
    admin = User(display_name="Admin", role="admin")
    ta = User(display_name="TA", role="ta")
    db.session.add_all([admin, ta])
    db.session.commit()

    login_as(client, ta)
    resp = client.post("/api/roster/import-enrollment", json={"csv": SAMPLE_ENROLLMENT})
    assert resp.status_code == 403

    login_as(client, admin)
    resp = client.post("/api/roster/import-enrollment", json={"csv": SAMPLE_ENROLLMENT})
    assert resp.status_code == 200
    assert resp.get_json()["summary"]["enrollments_created"] == 3
