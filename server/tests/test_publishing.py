"""Covers the draft/publish gate on assignments (Worksheet.is_published) and
the creation-order ordering of the class assignment list.
"""

from server.extensions import db
from server.models.group import Group, GroupMembership
from server.models.klass import Class
from server.models.section import Section
from server.models.user import User
from server.models.worksheet import Worksheet
from server.tests.conftest import login_as


def _make_class_with_users():
    ta = User(display_name="ta", role="ta")
    student = User(display_name="student", role="student")
    db.session.add_all([ta, student])
    db.session.flush()

    klass = Class(course_name="C")
    db.session.add(klass)
    db.session.flush()

    section = Section(class_id=klass.id, name="S", ta_user_id=ta.id)
    db.session.add(section)
    db.session.commit()
    return section, ta, student


def test_unpublished_worksheet_hidden_from_students_but_visible_to_ta(app, client):
    section, ta, student = _make_class_with_users()
    draft = Worksheet(class_id=section.class_id, slug="draft", title="Draft Assignment", is_published=False)
    released = Worksheet(class_id=section.class_id, slug="released", title="Released Assignment", is_published=True)
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
    worksheet = Worksheet(class_id=section.class_id, slug="draft", title="Draft", is_published=False)
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
    worksheet = Worksheet(class_id=section.class_id, slug="draft", title="Draft", is_published=False)
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
    draft = Worksheet(class_id=section.class_id, slug="draft", title="Draft", is_published=False)
    released = Worksheet(class_id=section.class_id, slug="released", title="Released", is_published=True)
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


def test_worksheets_ordered_by_creation(app, client):
    section, ta, _student = _make_class_with_users()

    first = Worksheet(class_id=section.class_id, slug="a", title="Made first")
    db.session.add(first)
    db.session.commit()

    second = Worksheet(class_id=section.class_id, slug="b", title="Made second")
    db.session.add(second)
    db.session.commit()

    login_as(client, ta)
    resp = client.get(f"/api/sections/{section.id}/worksheets")
    titles = [w["title"] for w in resp.get_json()["worksheets"]]

    assert titles == ["Made first", "Made second"]
