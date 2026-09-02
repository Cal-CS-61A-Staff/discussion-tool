"""Covers the draft/publish gate on assignments (Worksheet.is_published) and
the creation-order ordering of the class assignment list.
"""

from server.extensions import db
from server.models.group import Group, GroupMembership
from server.models.user import User
from server.models.worksheet import Worksheet
from server.tests.conftest import add_member, login_as, make_class


def _make_class_with_users():
    staff = User(display_name="staff", role="student")
    student = User(display_name="student", role="student")
    db.session.add_all([staff, student])
    db.session.flush()

    klass = make_class("C")
    add_member(staff, klass, "staff")
    add_member(student, klass, "student")
    db.session.commit()
    return klass, staff, student


def test_unpublished_worksheet_hidden_from_students_but_visible_to_staff(app, client):
    klass, staff, student = _make_class_with_users()
    db.session.add_all(
        [
            Worksheet(class_id=klass.id, slug="draft", title="Draft Assignment", is_published=False),
            Worksheet(class_id=klass.id, slug="released", title="Released Assignment", is_published=True),
        ]
    )
    db.session.commit()

    login_as(client, student)
    resp = client.get(f"/api/classes/{klass.id}/worksheets")
    assert [w["title"] for w in resp.get_json()["worksheets"]] == ["Released Assignment"]

    login_as(client, staff)
    resp = client.get(f"/api/classes/{klass.id}/worksheets")
    assert {w["title"] for w in resp.get_json()["worksheets"]} == {"Draft Assignment", "Released Assignment"}


def test_student_blocked_from_group_state_on_unpublished_worksheet(app, client):
    klass, staff, student = _make_class_with_users()
    worksheet = Worksheet(class_id=klass.id, slug="draft", title="Draft", is_published=False)
    db.session.add(worksheet)
    db.session.flush()

    group = Group(class_id=klass.id, number=1, name="G1")
    db.session.add(group)
    db.session.flush()
    db.session.add(GroupMembership(group_id=group.id, user_id=student.id))
    db.session.commit()

    login_as(client, student)
    assert client.get(f"/api/groups/{group.id}/state?worksheet_id={worksheet.id}").status_code == 403

    login_as(client, staff)
    resp = client.post(f"/api/worksheets/{worksheet.id}/publish")
    assert resp.status_code == 200
    assert resp.get_json()["worksheet"]["is_published"] is True

    login_as(client, student)
    assert client.get(f"/api/groups/{group.id}/state?worksheet_id={worksheet.id}").status_code == 200


def test_staff_can_still_access_unpublished_worksheet_state(app, client):
    klass, staff, student = _make_class_with_users()
    worksheet = Worksheet(class_id=klass.id, slug="draft", title="Draft", is_published=False)
    db.session.add(worksheet)
    db.session.flush()

    group = Group(class_id=klass.id, number=1, name="G1")
    db.session.add(group)
    db.session.flush()
    db.session.add(GroupMembership(group_id=group.id, user_id=student.id))
    db.session.commit()

    login_as(client, staff)
    assert client.get(f"/api/groups/{group.id}/state?worksheet_id={worksheet.id}").status_code == 200


def test_assignment_count_excludes_drafts_for_students(app, client):
    klass, staff, student = _make_class_with_users()
    db.session.add_all(
        [
            Worksheet(class_id=klass.id, slug="draft", title="Draft", is_published=False),
            Worksheet(class_id=klass.id, slug="released", title="Released", is_published=True),
        ]
    )
    db.session.commit()

    login_as(client, student)
    row = next(c for c in client.get("/api/classes").get_json()["classes"] if c["id"] == klass.id)
    assert row["assignment_count"] == 1

    login_as(client, staff)
    row = next(c for c in client.get("/api/classes").get_json()["classes"] if c["id"] == klass.id)
    assert row["assignment_count"] == 2


def test_worksheets_ordered_by_creation(app, client):
    klass, staff, _student = _make_class_with_users()

    db.session.add(Worksheet(class_id=klass.id, slug="a", title="Made first"))
    db.session.commit()
    db.session.add(Worksheet(class_id=klass.id, slug="b", title="Made second"))
    db.session.commit()

    login_as(client, staff)
    resp = client.get(f"/api/classes/{klass.id}/worksheets")
    assert [w["title"] for w in resp.get_json()["worksheets"]] == ["Made first", "Made second"]
