"""Covers TA-scoped-to-one-section access control, the admin role (grantable
out of band via server/app.py:create-admin, or by an existing admin through
POST /api/admins), and the group discussion history endpoint. Companion to
test_publishing.py, which already covers the plain student/ta
draft-visibility split this builds on top of.
"""

from server.extensions import db
from server.models.group import Group, GroupAssignmentProgress, GroupMembership
from server.models.klass import Class
from server.models.section import Section
from server.models.user import User
from server.models.worksheet import Question, Worksheet
from server.tests.conftest import login_as


def _make_two_sections_with_tas():
    ta_a = User(display_name="TA A", role="ta")
    ta_b = User(display_name="TA B", role="ta")
    admin = User(display_name="Admin", role="admin")
    db.session.add_all([ta_a, ta_b, admin])
    db.session.flush()

    klass = Class(course_name="C")
    db.session.add(klass)
    db.session.flush()

    section_a = Section(class_id=klass.id, name="Section A", ta_user_id=ta_a.id)
    section_b = Section(class_id=klass.id, name="Section B", ta_user_id=ta_b.id)
    db.session.add_all([section_a, section_b])
    db.session.commit()
    return section_a, section_b, ta_a, ta_b, admin


def test_ta_cannot_see_another_tas_section_groups(app, client):
    section_a, section_b, ta_a, ta_b, _admin = _make_two_sections_with_tas()
    group = Group(section_id=section_a.id, number=1, name="G1")
    db.session.add(group)
    db.session.commit()

    login_as(client, ta_b)
    resp = client.get(f"/api/sections/{section_a.id}/groups")
    assert resp.status_code == 403

    login_as(client, ta_a)
    resp = client.get(f"/api/sections/{section_a.id}/groups")
    assert resp.status_code == 200


def test_admin_can_manage_any_section(app, client):
    section_a, _section_b, _ta_a, _ta_b, admin = _make_two_sections_with_tas()

    login_as(client, admin)
    resp = client.get(f"/api/sections/{section_a.id}/groups")
    assert resp.status_code == 200

    resp = client.post(f"/api/sections/{section_a.id}/groups", json={"count": 1})
    assert resp.status_code == 201


def test_list_sections_scoped_to_own_ta(app, client):
    section_a, section_b, ta_a, _ta_b, admin = _make_two_sections_with_tas()

    login_as(client, ta_a)
    resp = client.get("/api/sections")
    ids = {s["id"] for s in resp.get_json()["sections"]}
    assert ids == {section_a.id}

    login_as(client, admin)
    resp = client.get("/api/sections")
    ids = {s["id"] for s in resp.get_json()["sections"]}
    assert ids == {section_a.id, section_b.id}


def test_unassigned_ta_sees_no_sections(app, client):
    _section_a, _section_b, _ta_a, _ta_b, _admin = _make_two_sections_with_tas()
    unassigned_ta = User(display_name="Unassigned", role="ta")
    db.session.add(unassigned_ta)
    db.session.commit()

    login_as(client, unassigned_ta)
    resp = client.get("/api/sections")
    assert resp.get_json()["sections"] == []


def test_only_admin_can_assign_section_ta(app, client):
    section_a, _section_b, ta_a, ta_b, admin = _make_two_sections_with_tas()

    login_as(client, ta_a)
    resp = client.put(f"/api/sections/{section_a.id}/ta", json={"ta_user_id": ta_b.id})
    assert resp.status_code == 403

    login_as(client, admin)
    resp = client.put(f"/api/sections/{section_a.id}/ta", json={"ta_user_id": ta_b.id})
    assert resp.status_code == 200
    assert resp.get_json()["section"]["ta_id"] == ta_b.id

    student = User(display_name="Student", role="student")
    db.session.add(student)
    db.session.commit()
    resp = client.put(f"/api/sections/{section_a.id}/ta", json={"ta_user_id": student.id})
    assert resp.status_code == 400


def test_group_history_visible_to_member_and_owning_ta_only(app, client):
    section_a, _section_b, ta_a, ta_b, _admin = _make_two_sections_with_tas()
    worksheet = Worksheet(class_id=section_a.class_id, slug="w1", title="Disc 1", is_published=True)
    db.session.add(worksheet)
    db.session.flush()
    db.session.add(Question(worksheet_id=worksheet.id, order_index=0, title="Q1", prompt="p"))

    group = Group(section_id=section_a.id, number=1, name="G1")
    db.session.add(group)
    db.session.flush()

    member = User(display_name="Member", role="student")
    outsider = User(display_name="Outsider", role="student")
    db.session.add_all([member, outsider])
    db.session.flush()
    db.session.add(GroupMembership(group_id=group.id, user_id=member.id))
    db.session.add(GroupAssignmentProgress(group_id=group.id, worksheet_id=worksheet.id, current_question_index=1))
    db.session.commit()

    login_as(client, member)
    resp = client.get(f"/api/groups/{group.id}/history")
    assert resp.status_code == 200
    history = resp.get_json()["history"]
    assert len(history) == 1
    assert history[0]["status"] == "completed"

    login_as(client, outsider)
    resp = client.get(f"/api/groups/{group.id}/history")
    assert resp.status_code == 403

    login_as(client, ta_a)
    resp = client.get(f"/api/groups/{group.id}/history")
    assert resp.status_code == 200

    login_as(client, ta_b)
    resp = client.get(f"/api/groups/{group.id}/history")
    assert resp.status_code == 403


def test_admin_can_grant_admin_role(app, client):
    _section_a, _section_b, ta_a, _ta_b, admin = _make_two_sections_with_tas()
    ta_a.email = "ta_a@berkeley.edu"
    db.session.commit()

    # A plain TA can't reach the endpoint at all.
    login_as(client, ta_a)
    resp = client.post("/api/admins", json={"email": "ta_a@berkeley.edu"})
    assert resp.status_code == 403

    # An admin can promote an existing TA — role flips, and (superset) the
    # section they owned is still theirs.
    login_as(client, admin)
    resp = client.post("/api/admins", json={"email": "TA_A@berkeley.edu"})
    assert resp.status_code == 201
    assert resp.get_json()["admin"]["role"] == "admin"
    assert ta_a.role == "admin"

    # A brand-new email creates the account with the admin role.
    resp = client.post("/api/admins", json={"email": "fresh@berkeley.edu", "name": "Fresh"})
    assert resp.status_code == 201
    created = User.query.filter_by(email="fresh@berkeley.edu").first()
    assert created is not None
    assert created.role == "admin"
    assert created.display_name == "Fresh"

    # Missing / malformed email is rejected.
    resp = client.post("/api/admins", json={"email": "not-an-email"})
    assert resp.status_code == 400


def test_admin_login_requires_admin_role(app, client):
    admin = User(display_name="Admin", role="admin")
    ta = User(display_name="TA", role="ta")
    db.session.add_all([admin, ta])
    db.session.commit()

    resp = client.post("/api/auth/admin-login", json={"admin_id": admin.id})
    assert resp.status_code == 200
    assert resp.get_json()["user"]["role"] == "admin"

    resp = client.post("/api/auth/admin-login", json={"admin_id": ta.id})
    assert resp.status_code == 404
