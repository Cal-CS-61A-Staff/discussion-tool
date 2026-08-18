"""Covers the draft/publish gate on assignments (Worksheet.is_published) and
the due-date-then-creation-date ordering of the class assignment list.
"""

from datetime import timedelta

from server.extensions import db
from server.models.group import Group, GroupMembership
from server.models.section import Section
from server.models.user import User
from server.models.worksheet import Worksheet
from server.tests.conftest import login_as
from server.utils import utcnow


def _make_class_with_users():
    section = Section(course_name="C", name="S")
    db.session.add(section)
    db.session.flush()

    ta = User(display_name="ta", role="ta")
    student = User(display_name="student", role="student")
    db.session.add_all([ta, student])
    db.session.commit()
    return section, ta, student


def test_unpublished_worksheet_hidden_from_students_but_visible_to_ta(app, client):
    section, ta, student = _make_class_with_users()
    draft = Worksheet(section_id=section.id, slug="draft", title="Draft Assignment", is_published=False)
    released = Worksheet(section_id=section.id, slug="released", title="Released Assignment", is_published=True)
    db.session.add_all([draft, released])
    db.session.commit()

    login_as(client, student)
    resp = client.get(f"/api/sections/{section.id}/worksheets")
    titles = [w["title"] for w in resp.get_json()["worksheets"]]
    assert titles == ["Released Assignment"]

    login_as(client, ta)
    resp = client.get(f"/api/sections/{section.id}/worksheets")
    titles = [w["title"] for w in resp.get_json()["worksheets"]]
    assert set(titles) == {"Draft Assignment", "Released Assignment"}


def test_student_blocked_from_group_state_on_unpublished_worksheet(app, client):
    section, ta, student = _make_class_with_users()
    worksheet = Worksheet(section_id=section.id, slug="draft", title="Draft", is_published=False)
    db.session.add(worksheet)
    db.session.flush()

    group = Group(section_id=section.id, number=1, name="G1")
    db.session.add(group)
    db.session.flush()
    db.session.add(GroupMembership(group_id=group.id, user_id=student.id))
    db.session.commit()

    login_as(client, student)
    resp = client.get(f"/api/groups/{group.id}/state?worksheet_id={worksheet.id}")
    assert resp.status_code == 403

    login_as(client, ta)
    resp = client.post(f"/api/worksheets/{worksheet.id}/publish")
    assert resp.status_code == 200
    assert resp.get_json()["worksheet"]["is_published"] is True

    login_as(client, student)
    resp = client.get(f"/api/groups/{group.id}/state?worksheet_id={worksheet.id}")
    assert resp.status_code == 200


def test_ta_can_still_access_unpublished_worksheet_state(app, client):
    section, ta, student = _make_class_with_users()
    worksheet = Worksheet(section_id=section.id, slug="draft", title="Draft", is_published=False)
    db.session.add(worksheet)
    db.session.flush()

    group = Group(section_id=section.id, number=1, name="G1")
    db.session.add(group)
    db.session.flush()
    db.session.add(GroupMembership(group_id=group.id, user_id=student.id))
    db.session.commit()

    login_as(client, ta)
    resp = client.get(f"/api/groups/{group.id}/state?worksheet_id={worksheet.id}")
    assert resp.status_code == 200


def test_worksheet_count_excludes_drafts_for_students(app, client):
    section, ta, student = _make_class_with_users()
    draft = Worksheet(section_id=section.id, slug="draft", title="Draft", is_published=False)
    released = Worksheet(section_id=section.id, slug="released", title="Released", is_published=True)
    db.session.add_all([draft, released])
    db.session.commit()

    login_as(client, student)
    resp = client.get("/api/sections")
    row = next(s for s in resp.get_json()["sections"] if s["id"] == section.id)
    assert row["worksheet_count"] == 1

    login_as(client, ta)
    resp = client.get("/api/sections")
    row = next(s for s in resp.get_json()["sections"] if s["id"] == section.id)
    assert row["worksheet_count"] == 2


def test_worksheets_ordered_by_due_date_then_creation(app, client):
    section, ta, _student = _make_class_with_users()
    # created_at uses utcnow() (server/utils.py), so derive "today" from the
    # same clock — using the local date.today() here could momentarily
    # disagree near a UTC day boundary and make this test flaky.
    today = utcnow().date()

    # Created in an order that would be wrong if we sorted by id/creation
    # alone: "No due date, made first" should land between the two dated
    # ones once due dates are taken into account, and "No due date, made
    # last" (no due date) should sort by its own creation time.
    no_date_first = Worksheet(section_id=section.id, slug="a", title="No due date, made first")
    db.session.add(no_date_first)
    db.session.commit()

    due_later = Worksheet(section_id=section.id, slug="b", title="Due later", due_date=today + timedelta(days=10))
    due_soon = Worksheet(section_id=section.id, slug="c", title="Due soon", due_date=today + timedelta(days=1))
    db.session.add_all([due_later, due_soon])
    db.session.commit()

    no_date_first.due_date = None  # explicit, no due date set
    db.session.commit()

    login_as(client, ta)
    resp = client.get(f"/api/sections/{section.id}/worksheets")
    titles = [w["title"] for w in resp.get_json()["worksheets"]]

    # "No due date, made first" was created before the dated ones, so its
    # creation-date fallback sorts it ahead of both; the dated ones then
    # follow in due-date order.
    assert titles == ["No due date, made first", "Due soon", "Due later"]
