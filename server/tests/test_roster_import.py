"""Covers the staff roster CSV import (columns Name, Email, Sections) and
the login-time persistence it enables — see server/services/roster_import.py.
"""

from server.extensions import db
from server.models.klass import Class, ClassMembership
from server.models.section import Section
from server.models.user import User
from server.services.roster_import import (
    find_ta_by_name,
    find_user_by_email,
    import_ta_roster,
    parse_ta_roster,
)
from server.tests.conftest import login_as

SAMPLE_ROSTER = (
    "Name,Email,Sections\n"
    "Alex Yang,alex@berkeley.edu,R 2:00 PM (VLSB2070); R 3:30 PM (VLSB2070)\n"
    "Bill Taing,bill@berkeley.edu,R 2:00 PM (VLSB2066); W 5:00 PM (CORY247)\n"
    "Sultan Muratbek,sultan@berkeley.edu,\n"
    "Sriya Kalyan,sriya@berkeley.edu,R 3:30 PM (PHYS3); N/A\n"
    "\n"
)


def test_parse_ta_roster_reads_name_email_and_sections():
    entries = parse_ta_roster(SAMPLE_ROSTER)
    by_name = {e["name"]: e for e in entries}

    assert by_name["Alex Yang"]["email"] == "alex@berkeley.edu"
    assert by_name["Alex Yang"]["sections"] == ["R 2:00 PM (VLSB2070)", "R 3:30 PM (VLSB2070)"]
    assert by_name["Bill Taing"]["sections"] == ["R 2:00 PM (VLSB2066)", "W 5:00 PM (CORY247)"]
    assert by_name["Sultan Muratbek"]["sections"] == []
    assert by_name["Sriya Kalyan"]["sections"] == ["R 3:30 PM (PHYS3)"]
    assert "" not in by_name


def test_parse_ta_roster_tolerates_tab_separated_paste():
    entries = parse_ta_roster("Name\tEmail\tSections\nAlex Yang\talex@berkeley.edu\tR 2:00 PM (VLSB2070)\n")
    assert entries[0]["email"] == "alex@berkeley.edu"
    assert entries[0]["sections"] == ["R 2:00 PM (VLSB2070)"]


def test_import_ta_roster_creates_staff_and_assigns_rooms(app, db):
    summary = import_ta_roster(SAMPLE_ROSTER)

    assert summary["tas_created"] == 4
    assert summary["sections_created"] == 5  # 2 + 2 + 0 + 1

    alex = find_user_by_email("alex@berkeley.edu")
    assert alex is not None

    klass = Class.query.filter_by(course_name="CS 61A").first()
    # Granted class staff, and made the room's TA.
    assert ClassMembership.query.filter_by(user_id=alex.id, class_id=klass.id, role="staff").count() == 1
    room = Section.query.filter_by(class_id=klass.id, name="R 2:00 PM (VLSB2070)").first()
    assert room.ta_user_id == alex.id

    # Someone with zero rooms still gets a class-staff membership.
    sultan = find_user_by_email("sultan@berkeley.edu")
    assert ClassMembership.query.filter_by(user_id=sultan.id, class_id=klass.id, role="staff").count() == 1


def test_import_ta_roster_is_idempotent(app, db):
    import_ta_roster(SAMPLE_ROSTER)
    summary = import_ta_roster(SAMPLE_ROSTER)

    assert summary["tas_created"] == 0
    assert summary["tas_matched"] == 4
    assert summary["sections_created"] == 0
    assert summary["sections_assigned"] == 5

    klass = Class.query.filter_by(course_name="CS 61A").first()
    alex = find_user_by_email("alex@berkeley.edu")
    assert ClassMembership.query.filter_by(user_id=alex.id, class_id=klass.id).count() == 1


def test_login_reuses_roster_matched_account_by_email(app, client, db):
    import_ta_roster(SAMPLE_ROSTER)
    alex = find_user_by_email("alex@berkeley.edu")

    resp = client.post(
        "/api/auth/login", json={"display_name": "Alex Y", "role": "student", "email": "alex@berkeley.edu"}
    )
    assert resp.status_code == 200
    assert resp.get_json()["user"]["id"] == alex.id


def test_import_roster_endpoint_is_admin_only(app, client, db):
    admin = User(display_name="Admin", role="admin")
    plain = User(display_name="Plain", role="student")
    db.session.add_all([admin, plain])
    db.session.commit()

    login_as(client, plain)
    assert client.post("/api/roster/import", json={"csv": SAMPLE_ROSTER}).status_code == 403

    login_as(client, admin)
    resp = client.post("/api/roster/import", json={"csv": SAMPLE_ROSTER})
    assert resp.status_code == 200
    assert resp.get_json()["summary"]["tas_created"] == 4
