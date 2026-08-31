"""Covers importing the staff-assignment sheet (TA name + repeating
Section/Groups column pairs) and the login-time TA persistence it enables —
see server/services/roster_import.py.
"""

from server.extensions import db
from server.models.klass import Class
from server.models.section import Section
from server.models.user import User
from server.services.roster_import import find_ta_by_name, import_ta_roster, parse_ta_roster
from server.tests.conftest import login_as

SAMPLE_ROSTER = (
    "TA\tSection 1\tGroups\tSection 2\tGroups\tSection 3\tGroups\tSection 4\tGroups\t\n"
    "Alex Yang\tR 2:00 PM-3:29 PM (VLSB2070)\t188-193\tR 3:30 PM-4:59 PM (VLSB2070)\t194-197\t\t\t\t\t\n"
    "Bill Taing\tR 2:00 PM-3:29 PM (VLSB2066)\t182-187\tR 3:30 PM-4:59 PM (VLSB2038)\t152-156\t"
    "W 5:00 PM-6:29 PM (CORY247)\t18-25\t\t\t\n"
    "Sultan Muratbek\t\t\t\t\t\t\t\t\t\n"
    "Sriya Kalyan\tR 3:30 PM-4:59 PM (PHYS3)\tN/A\tR 5:00 PM-6:29 PM (VLSB2032)\t146-151\t\t\t\t\t\n"
    "\t\t\t\t\t\t\t\t\t\n"
)


def test_parse_ta_roster_reads_names_and_section_labels():
    entries = parse_ta_roster(SAMPLE_ROSTER)
    by_name = {e["name"]: e["sections"] for e in entries}

    assert by_name["Alex Yang"] == ["R 2:00 PM-3:29 PM (VLSB2070)", "R 3:30 PM-4:59 PM (VLSB2070)"]
    assert by_name["Bill Taing"] == [
        "R 2:00 PM-3:29 PM (VLSB2066)",
        "R 3:30 PM-4:59 PM (VLSB2038)",
        "W 5:00 PM-6:29 PM (CORY247)",
    ]
    # No sections listed at all -- still a valid entry, just an empty list.
    assert by_name["Sultan Muratbek"] == []
    # "N/A" groups cell doesn't affect the (non-"N/A") section label itself.
    assert by_name["Sriya Kalyan"] == ["R 3:30 PM-4:59 PM (PHYS3)", "R 5:00 PM-6:29 PM (VLSB2032)"]
    # Blank trailing row is skipped, not turned into a bogus entry.
    assert "" not in by_name


def test_parse_ta_roster_also_accepts_a_real_comma_separated_csv():
    """The Admin page now uploads an actual .csv file (comma-separated)
    instead of a Google Sheets tab-separated paste — the delimiter is
    auto-detected, so both work."""
    csv_text = (
        "TA,Section 1,Groups\n"
        "Alex Yang,R 2:00 PM-3:29 PM (VLSB2070),188-193\n"
    )
    entries = parse_ta_roster(csv_text)
    by_name = {e["name"]: e["sections"] for e in entries}
    assert by_name["Alex Yang"] == ["R 2:00 PM-3:29 PM (VLSB2070)"]


def test_import_ta_roster_creates_tas_and_assigns_sections(app, db):
    summary = import_ta_roster(SAMPLE_ROSTER)

    assert summary["tas_created"] == 4
    assert summary["sections_created"] == 7  # 2 + 3 + 0 + 2

    alex = find_ta_by_name("Alex Yang")
    assert alex is not None
    assert alex.role == "ta"

    klass = Class.query.filter_by(course_name="CS 61A").first()
    assert klass is not None
    section = Section.query.filter_by(class_id=klass.id, name="R 2:00 PM-3:29 PM (VLSB2070)").first()
    assert section is not None
    assert section.ta_user_id == alex.id

    sultan = find_ta_by_name("Sultan Muratbek")
    assert sultan is not None  # created even with zero sections

    # Name matching is case-insensitive/trimmed.
    assert find_ta_by_name("  alex yang ") is not None


def test_import_ta_roster_is_idempotent(app, db):
    import_ta_roster(SAMPLE_ROSTER)
    summary = import_ta_roster(SAMPLE_ROSTER)

    assert summary["tas_created"] == 0
    assert summary["tas_matched"] == 4
    assert summary["sections_created"] == 0
    assert summary["sections_assigned"] == 7


def test_ta_login_reuses_roster_matched_account_by_name(app, client, db):
    import_ta_roster(SAMPLE_ROSTER)
    alex = find_ta_by_name("Alex Yang")

    resp = client.post("/api/auth/login", json={"display_name": "Alex Yang", "role": "ta"})
    assert resp.status_code == 200
    assert resp.get_json()["user"]["id"] == alex.id

    # Case/whitespace-insensitive match too.
    resp = client.post("/api/auth/login", json={"display_name": "  alex yang  ", "role": "ta"})
    assert resp.get_json()["user"]["id"] == alex.id


def test_ta_login_still_creates_new_account_when_not_on_roster(app, client, db):
    resp = client.post("/api/auth/login", json={"display_name": "Nobody On The Roster", "role": "ta"})
    assert resp.status_code == 200
    assert resp.get_json()["user"]["role"] == "ta"


def test_student_login_always_creates_a_new_user_even_with_matching_name(app, client, db):
    # Roster matching is TA-only -- a student is never deduped against
    # anything, even if their name happens to collide with a TA's.
    import_ta_roster(SAMPLE_ROSTER)

    resp1 = client.post("/api/auth/login", json={"display_name": "Alex Yang", "role": "student"})
    resp2 = client.post("/api/auth/login", json={"display_name": "Alex Yang", "role": "student"})
    assert resp1.get_json()["user"]["id"] != resp2.get_json()["user"]["id"]


def test_import_roster_endpoint_is_admin_only(app, client, db):
    admin = User(display_name="Admin", role="admin")
    ta = User(display_name="TA", role="ta")
    db.session.add_all([admin, ta])
    db.session.commit()

    login_as(client, ta)
    resp = client.post("/api/roster/import", json={"csv": SAMPLE_ROSTER})
    assert resp.status_code == 403

    login_as(client, admin)
    resp = client.post("/api/roster/import", json={"csv": SAMPLE_ROSTER})
    assert resp.status_code == 200
    assert resp.get_json()["summary"]["tas_created"] == 4
