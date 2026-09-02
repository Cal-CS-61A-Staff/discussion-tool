"""Per-class roles: staff standing lives on ClassMembership, not the global
User.role (only 'admin' is global now). Covers the class-scoped access
checks, room listing, room-TA assignment, group history visibility, and
admin granting.
"""

from server.extensions import db
from server.models.group import Group, GroupAssignmentProgress, GroupMembership
from server.models.klass import ClassMembership
from server.models.section import Section
from server.models.user import User
from server.models.worksheet import Question, Worksheet
from server.tests.conftest import add_member, login_as, make_class


def _two_classes_with_staff():
    staff_a = User(display_name="Staff A", role="student")
    staff_b = User(display_name="Staff B", role="student")
    admin = User(display_name="Admin", role="admin")
    db.session.add_all([staff_a, staff_b, admin])
    db.session.flush()

    class_a = make_class("CS 61A", "AAAAAA")
    class_b = make_class("CS 88", "BBBBBB")
    add_member(staff_a, class_a, "staff")
    add_member(staff_b, class_b, "staff")

    room_a = Section(class_id=class_a.id, name="Room A", ta_user_id=staff_a.id, assigned_numbers="1-4")
    room_b = Section(class_id=class_b.id, name="Room B", ta_user_id=staff_b.id, assigned_numbers="1-4")
    db.session.add_all([room_a, room_b])
    db.session.commit()
    return class_a, class_b, room_a, room_b, staff_a, staff_b, admin


def test_list_sections_scoped_to_staffed_classes(app, client):
    _class_a, _class_b, room_a, room_b, staff_a, _staff_b, admin = _two_classes_with_staff()

    login_as(client, staff_a)
    ids = {s["id"] for s in client.get("/api/sections").get_json()["sections"]}
    assert ids == {room_a.id}

    login_as(client, admin)
    ids = {s["id"] for s in client.get("/api/sections").get_json()["sections"]}
    assert ids == {room_a.id, room_b.id}


def test_user_with_no_staff_membership_sees_no_rooms(app, client):
    _two_classes_with_staff()
    nobody = User(display_name="Nobody", role="student")
    db.session.add(nobody)
    db.session.commit()

    login_as(client, nobody)
    assert client.get("/api/sections").get_json()["sections"] == []


def test_staff_of_one_class_cannot_touch_another_classes_rooms(app, client):
    _class_a, _class_b, _room_a, room_b, staff_a, _staff_b, _admin = _two_classes_with_staff()

    login_as(client, staff_a)
    resp = client.put(f"/api/sections/{room_b.id}/details", json={"name": "hijacked"})
    assert resp.status_code == 403


def test_only_admin_can_assign_room_ta(app, client):
    class_a, _class_b, room_a, _room_b, staff_a, _staff_b, admin = _two_classes_with_staff()
    other_staff = User(display_name="Other", role="student")
    db.session.add(other_staff)
    db.session.flush()
    add_member(other_staff, class_a, "staff")
    db.session.commit()

    login_as(client, staff_a)
    resp = client.put(f"/api/sections/{room_a.id}/ta", json={"ta_user_id": other_staff.id})
    assert resp.status_code == 403

    login_as(client, admin)
    resp = client.put(f"/api/sections/{room_a.id}/ta", json={"ta_user_id": other_staff.id})
    assert resp.status_code == 200
    assert resp.get_json()["section"]["ta_id"] == other_staff.id

    # A person who isn't staff of this class can't be its room TA.
    stranger = User(display_name="Stranger", role="student")
    db.session.add(stranger)
    db.session.commit()
    resp = client.put(f"/api/sections/{room_a.id}/ta", json={"ta_user_id": stranger.id})
    assert resp.status_code == 400


def test_group_history_visible_to_member_and_class_staff_only(app, client):
    class_a, _class_b, _room_a, _room_b, staff_a, staff_b, _admin = _two_classes_with_staff()
    worksheet = Worksheet(class_id=class_a.id, slug="w1", title="Disc 1", is_published=True)
    db.session.add(worksheet)
    db.session.flush()
    db.session.add(Question(worksheet_id=worksheet.id, order_index=0, title="Q1", prompt="p"))

    group = Group(class_id=class_a.id, number=1, name="G1")
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
    assert resp.get_json()["history"][0]["status"] == "completed"

    login_as(client, outsider)
    assert client.get(f"/api/groups/{group.id}/history").status_code == 403

    login_as(client, staff_a)  # staff of this class
    assert client.get(f"/api/groups/{group.id}/history").status_code == 200

    login_as(client, staff_b)  # staff of a different class
    assert client.get(f"/api/groups/{group.id}/history").status_code == 403


def test_admin_can_grant_admin_role(app, client):
    class_a, _class_b, _room_a, _room_b, staff_a, _staff_b, admin = _two_classes_with_staff()
    staff_a.email = "staff_a@berkeley.edu"
    db.session.commit()

    login_as(client, staff_a)
    assert client.post("/api/admins", json={"email": "staff_a@berkeley.edu"}).status_code == 403

    login_as(client, admin)
    resp = client.post("/api/admins", json={"email": "STAFF_A@berkeley.edu"})
    assert resp.status_code == 201
    assert resp.get_json()["admin"]["role"] == "admin"
    assert staff_a.role == "admin"

    resp = client.post("/api/admins", json={"email": "fresh@berkeley.edu", "name": "Fresh"})
    assert resp.status_code == 201
    created = User.query.filter_by(email="fresh@berkeley.edu").first()
    assert created is not None and created.role == "admin" and created.display_name == "Fresh"

    assert client.post("/api/admins", json={"email": "not-an-email"}).status_code == 400


def test_admin_login_requires_admin_role(app, client):
    admin = User(display_name="Admin", role="admin")
    plain = User(display_name="Plain", role="student")
    db.session.add_all([admin, plain])
    db.session.commit()

    resp = client.post("/api/auth/admin-login", json={"admin_id": admin.id})
    assert resp.status_code == 200
    assert resp.get_json()["user"]["role"] == "admin"

    assert client.post("/api/auth/admin-login", json={"admin_id": plain.id}).status_code == 404


def test_join_class_by_code_and_scoping(app, client):
    class_a, class_b, _room_a, _room_b, _staff_a, _staff_b, _admin = _two_classes_with_staff()
    worksheet = Worksheet(class_id=class_b.id, slug="wb", title="B Disc", is_published=True)
    db.session.add(worksheet)
    db.session.commit()

    student = User(display_name="Stu", role="student")
    db.session.add(student)
    db.session.commit()
    login_as(client, student)

    # Not in class_b yet — can't see its assignments.
    assert client.get(f"/api/classes/{class_b.id}/worksheets").status_code == 403

    resp = client.post("/api/classes/join", json={"code": "bbbbbb"})  # case-insensitive
    assert resp.status_code == 200
    assert resp.get_json()["klass"]["my_role"] == "student"
    assert ClassMembership.query.filter_by(user_id=student.id, class_id=class_b.id).count() == 1

    resp = client.get(f"/api/classes/{class_b.id}/worksheets")
    assert resp.status_code == 200
    assert [w["title"] for w in resp.get_json()["worksheets"]] == ["B Disc"]

    # class_a still invisible.
    assert client.get("/api/classes").get_json()["classes"] == [
        c for c in client.get("/api/classes").get_json()["classes"] if c["id"] == class_b.id
    ]

    assert client.post("/api/classes/join", json={"code": "NOPE99"}).status_code == 404
