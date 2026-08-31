"""Covers the TA roster CSV import (columns Name, Email, Sections) and the
login-time TA persistence it enables — see server/services/roster_import.py.
"""

from server.extensions import db
from server.models.klass import Class
from server.models.section import Section
from server.models.user import User
from server.services.roster_import import (
    add_ta_by_email,
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
    # "N/A" entries are dropped.
    assert by_name["Sriya Kalyan"]["sections"] == ["R 3:30 PM (PHYS3)"]
    assert "" not in by_name


def test_parse_ta_roster_tolerates_tab_separated_paste():
    entries = parse_ta_roster("Name\tEmail\tSections\nAlex Yang\talex@berkeley.edu\tR 2:00 PM (VLSB2070)\n")
    assert entries[0]["email"] == "alex@berkeley.edu"
    assert entries[0]["sections"] == ["R 2:00 PM (VLSB2070)"]


def test_import_ta_roster_creates_tas_and_assigns_sections(app, db):
    summary = import_ta_roster(SAMPLE_ROSTER)

    assert summary["tas_created"] == 4
    assert summary["sections_created"] == 5  # 2 + 2 + 0 + 1

    alex = find_user_by_email("alex@berkeley.edu")
    assert alex is not None and alex.role == "ta"

    klass = Class.query.filter_by(course_name="CS 61A").first()
    section = Section.query.filter_by(class_id=klass.id, name="R 2:00 PM (VLSB2070)").first()
    assert section.ta_user_id == alex.id

    assert find_user_by_email("sultan@berkeley.edu") is not None  # created with zero sections


def test_import_ta_roster_is_idempotent(app, db):
    import_ta_roster(SAMPLE_ROSTER)
    summary = import_ta_roster(SAMPLE_ROSTER)

    assert summary["tas_created"] == 0
    assert summary["tas_matched"] == 4
    assert summary["sections_created"] == 0
    assert summary["sections_assigned"] == 5


def test_ta_login_reuses_roster_matched_account_by_email(app, client, db):
    import_ta_roster(SAMPLE_ROSTER)
    alex = find_user_by_email("alex@berkeley.edu")

    resp = client.post("/api/auth/login", json={"display_name": "Alex Y", "role": "ta", "email": "alex@berkeley.edu"})
    assert resp.status_code == 200
    assert resp.get_json()["user"]["id"] == alex.id


def test_add_ta_by_email_creates_or_promotes(app, db):
    ta = add_ta_by_email("newta@berkeley.edu", "New TA")
    assert ta.role == "ta" and ta.display_name == "New TA"

    student = User(display_name="Was Student", role="student", email="promote@berkeley.edu")
    db.session.add(student)
    db.session.commit()
    promoted = add_ta_by_email("promote@berkeley.edu")
    assert promoted.id == student.id and promoted.role == "ta"


def test_import_roster_endpoint_is_admin_only(app, client, db):
    admin = User(display_name="Admin", role="admin")
    ta = User(display_name="TA", role="ta")
    db.session.add_all([admin, ta])
    db.session.commit()

    login_as(client, ta)
    assert client.post("/api/roster/import", json={"csv": SAMPLE_ROSTER}).status_code == 403

    login_as(client, admin)
    resp = client.post("/api/roster/import", json={"csv": SAMPLE_ROSTER})
    assert resp.status_code == 200
    assert resp.get_json()["summary"]["tas_created"] == 4


def test_add_ta_endpoint_is_admin_only(app, client, db):
    admin = User(display_name="Admin", role="admin")
    ta = User(display_name="TA", role="ta")
    db.session.add_all([admin, ta])
    db.session.commit()

    login_as(client, ta)
    assert client.post("/api/tas", json={"email": "x@berkeley.edu"}).status_code == 403

    login_as(client, admin)
    resp = client.post("/api/tas", json={"email": "x@berkeley.edu", "name": "X"})
    assert resp.status_code == 201
    assert resp.get_json()["ta"]["role"] == "ta"
    assert find_user_by_email("x@berkeley.edu") is not None
