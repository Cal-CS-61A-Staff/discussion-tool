"""Assignments belong to a Class and are shared across it; any class staff
can author them. Per-class roles come from ClassMembership. Also covers
join-by-number, the group-name endpoint, and the watch-list dashboard.
"""

from server.extensions import db
from server.models.group import Group, GroupAssignmentProgress, GroupMembership
from server.models.klass import ClassMembership
from server.models.rating import Rating
from server.models.section import Section
from server.models.ta_watch import TaWatchedNumber
from server.models.user import User
from server.models.worksheet import Question, Worksheet
from server.tests.conftest import add_member, login_as, make_class


def _make_class():
    staff = User(display_name="Staff", role="student")
    other_staff = User(display_name="Other Staff", role="student")
    outsider = User(display_name="Outsider", role="student")
    admin = User(display_name="Admin", role="admin")
    db.session.add_all([staff, other_staff, outsider, admin])
    db.session.flush()

    klass = make_class("CS 61A")
    add_member(staff, klass, "staff")
    add_member(other_staff, klass, "staff")
    db.session.commit()
    return klass, staff, other_staff, outsider, admin


def test_any_class_staff_can_author_an_assignment(app, client, db):
    klass, staff, other_staff, outsider, admin = _make_class()

    login_as(client, outsider)
    assert client.post(f"/api/classes/{klass.id}/worksheets", json={"title": "Disc 1"}).status_code == 403

    login_as(client, staff)
    resp = client.post(f"/api/classes/{klass.id}/worksheets", json={"title": "Disc 1"})
    assert resp.status_code == 201
    worksheet_id = resp.get_json()["worksheet"]["id"]

    login_as(client, other_staff)
    resp = client.put(f"/api/worksheets/{worksheet_id}", json={"title": "Disc 1 (edited)"})
    assert resp.status_code == 200

    login_as(client, admin)
    assert client.post(f"/api/worksheets/{worksheet_id}/publish").status_code == 200


def test_question_endpoints_use_class_staff_access(app, client, db):
    klass, staff, other_staff, outsider, _admin = _make_class()

    login_as(client, staff)
    worksheet_id = client.post(f"/api/classes/{klass.id}/worksheets", json={"title": "Disc"}).get_json()["worksheet"]["id"]

    login_as(client, outsider)
    assert client.get(f"/api/worksheets/{worksheet_id}/questions").status_code == 403

    login_as(client, other_staff)
    assert client.get(f"/api/worksheets/{worksheet_id}/questions").status_code == 200


def test_worksheet_grades_span_every_group_in_the_class(app, client, db):
    klass, staff, _other, _outsider, _admin = _make_class()

    login_as(client, staff)
    worksheet_id = client.post(f"/api/classes/{klass.id}/worksheets", json={"title": "Disc"}).get_json()["worksheet"]["id"]

    g1 = Group(class_id=klass.id, number=1, name="G1")
    g2 = Group(class_id=klass.id, number=2, name="G2")
    db.session.add_all([g1, g2])
    db.session.commit()

    resp = client.get(f"/api/worksheets/{worksheet_id}/grades")
    assert resp.status_code == 200
    assert {row["group_id"] for row in resp.get_json()["groups"]} == {g1.id, g2.id}


def test_work_individually_reuses_one_solo_group_and_needs_membership(app, client, db):
    klass, staff, _other, outsider, _admin = _make_class()

    login_as(client, outsider)  # not a member of the class
    assert client.post(f"/api/classes/{klass.id}/work-individually").status_code == 403

    login_as(client, staff)  # staff are class members
    resp = client.post(f"/api/classes/{klass.id}/work-individually")
    assert resp.status_code == 200
    group = resp.get_json()["group"]
    assert group["is_individual"] is True
    resp2 = client.post(f"/api/classes/{klass.id}/work-individually")
    assert resp2.get_json()["group"]["id"] == group["id"]


def test_worksheet_grades_excludes_a_staff_preview_group(app, client, db):
    klass, staff, _other, _outsider, _admin = _make_class()

    login_as(client, staff)
    worksheet_id = client.post(f"/api/classes/{klass.id}/worksheets", json={"title": "Disc"}).get_json()["worksheet"]["id"]
    staff_group_id = client.post(f"/api/classes/{klass.id}/work-individually").get_json()["group"]["id"]

    student = User(display_name="Student", role="student")
    db.session.add(student)
    db.session.flush()
    add_member(student, klass, "student")
    db.session.commit()
    login_as(client, student)
    student_group_id = client.post(f"/api/classes/{klass.id}/work-individually").get_json()["group"]["id"]

    login_as(client, staff)
    ids = {row["group_id"] for row in client.get(f"/api/worksheets/{worksheet_id}/grades").get_json()["groups"]}
    assert student_group_id in ids
    assert staff_group_id not in ids


def test_list_classes_scoped_by_membership(app, client, db):
    klass, staff, _other, outsider, admin = _make_class()

    login_as(client, staff)
    assert {c["id"] for c in client.get("/api/classes").get_json()["classes"]} == {klass.id}
    assert next(c for c in client.get("/api/classes").get_json()["classes"])["my_role"] == "staff"

    login_as(client, outsider)
    assert client.get("/api/classes").get_json()["classes"] == []

    login_as(client, admin)
    assert {c["id"] for c in client.get("/api/classes").get_json()["classes"]} == {klass.id}


def test_only_an_admin_can_create_a_class(app, client, db):
    plain = User(display_name="Plain", role="student")
    admin = User(display_name="Admin", role="admin")
    db.session.add_all([plain, admin])
    db.session.commit()

    login_as(client, plain)
    resp = client.post("/api/classes", json={"course_name": "CS 61B"})
    assert resp.status_code == 403

    login_as(client, admin)
    resp = client.post("/api/classes", json={"course_name": "CS 61D"})
    assert resp.status_code == 201
    assert resp.get_json()["klass"]["is_archived"] is False
    assert resp.get_json()["klass"]["join_code"]


def test_only_an_admin_can_archive_a_class(app, client, db):
    klass, staff, _other, _outsider, admin = _make_class()

    login_as(client, staff)
    assert client.put(f"/api/classes/{klass.id}/archive", json={"is_archived": True}).status_code == 403

    login_as(client, admin)
    resp = client.put(f"/api/classes/{klass.id}/archive", json={"is_archived": True})
    assert resp.status_code == 200
    assert resp.get_json()["klass"]["is_archived"] is True


def test_class_worksheets_includes_a_students_own_rating(app, client, db):
    klass, staff, _other, _outsider, _admin = _make_class()
    worksheet = Worksheet(class_id=klass.id, slug="w1", title="Disc 1", is_published=True)
    db.session.add(worksheet)
    db.session.flush()
    question = Question(worksheet_id=worksheet.id, order_index=0, title="Q1", prompt="p")
    db.session.add(question)
    db.session.flush()

    student = User(display_name="Student", role="student")
    db.session.add(student)
    db.session.flush()
    add_member(student, klass, "student")
    group = Group(class_id=klass.id, number=1, name="G1")
    db.session.add(group)
    db.session.flush()
    db.session.add(GroupMembership(group_id=group.id, user_id=student.id))
    db.session.commit()

    login_as(client, student)
    payload = client.get(f"/api/classes/{klass.id}/worksheets").get_json()["worksheets"][0]
    assert payload["my_rating"] is None and payload["my_group_id"] is None

    db.session.add(GroupAssignmentProgress(group_id=group.id, worksheet_id=worksheet.id, current_question_index=0))
    db.session.add(Rating(group_id=group.id, question_id=question.id, user_id=student.id, value=5))
    db.session.commit()

    payload = client.get(f"/api/classes/{klass.id}/worksheets").get_json()["worksheets"][0]
    assert payload["my_rating"] == 5.0 and payload["my_group_id"] == group.id


def test_join_by_number_creates_one_shared_group_and_names_it(app, client, db):
    klass, _staff, _other, _outsider, _admin = _make_class()
    a = User(display_name="A", role="student")
    b = User(display_name="B", role="student")
    db.session.add_all([a, b])
    db.session.flush()
    add_member(a, klass, "student")
    add_member(b, klass, "student")
    db.session.commit()

    login_as(client, a)
    resp = client.post(f"/api/classes/{klass.id}/groups/join", json={"number": 7, "name": "Otters"})
    assert resp.status_code == 200
    group_id = resp.get_json()["group"]["id"]
    assert resp.get_json()["group"]["name"] == "Otters"

    login_as(client, b)
    resp = client.post(f"/api/classes/{klass.id}/groups/join", json={"number": 7})
    assert resp.get_json()["group"]["id"] == group_id  # same group

    assert Group.query.filter_by(class_id=klass.id, number=7, is_individual=False).count() == 1
    assert GroupMembership.query.filter_by(group_id=group_id).count() == 2

    # any member can rename it
    resp = client.put(f"/api/groups/{group_id}/name", json={"name": "Sea Otters"})
    assert resp.status_code == 200
    assert db.session.get(Group, group_id).name == "Sea Otters"

    # a non-member can't
    outsider = User(display_name="Nope", role="student")
    db.session.add(outsider)
    db.session.commit()
    login_as(client, outsider)
    assert client.put(f"/api/groups/{group_id}/name", json={"name": "hax"}).status_code == 403


def test_join_by_number_requires_class_membership(app, client, db):
    klass, _staff, _other, outsider, _admin = _make_class()
    login_as(client, outsider)
    assert client.post(f"/api/classes/{klass.id}/groups/join", json={"number": 3}).status_code == 403


def test_watch_list_seeds_from_rooms_then_is_editable(app, client, db):
    klass, staff, _other, _outsider, _admin = _make_class()
    room = Section(class_id=klass.id, name="Room", ta_user_id=staff.id, assigned_numbers="1-3")
    db.session.add(room)
    db.session.commit()

    login_as(client, staff)
    resp = client.get(f"/api/classes/{klass.id}/watched-numbers")
    assert resp.get_json()["numbers"] == [1, 2, 3]

    resp = client.put(f"/api/classes/{klass.id}/watched-numbers", json={"numbers": [2, 5, 5, 9]})
    assert resp.get_json()["numbers"] == [2, 5, 9]
    assert sorted(r.number for r in TaWatchedNumber.query.filter_by(user_id=staff.id).all()) == [2, 5, 9]


def test_dashboard_has_one_tile_per_watched_number(app, client, db):
    klass, staff, _other, _outsider, _admin = _make_class()
    room = Section(class_id=klass.id, name="Room", ta_user_id=staff.id, assigned_numbers="1-2")
    db.session.add(room)
    db.session.flush()
    worksheet = Worksheet(class_id=klass.id, slug="w", title="W", is_published=True)
    db.session.add(worksheet)
    db.session.flush()
    db.session.add(Question(worksheet_id=worksheet.id, order_index=0, title="Q", prompt="p"))

    # someone entered number 1
    student = User(display_name="Stu", role="student")
    db.session.add(student)
    db.session.flush()
    add_member(student, klass, "student")
    g1 = Group(class_id=klass.id, number=1, name="Group 1")
    db.session.add(g1)
    db.session.flush()
    db.session.add(GroupMembership(group_id=g1.id, user_id=student.id))
    db.session.commit()

    login_as(client, student)
    client.get(f"/api/groups/{g1.id}/state?worksheet_id={worksheet.id}")  # mark present

    login_as(client, staff)
    tiles = client.get(f"/api/worksheets/{worksheet.id}/dashboard").get_json()["groups"]
    by_number = {t["number"]: t for t in tiles}
    assert set(by_number) == {1, 2}
    assert by_number[1]["present"] == ["Stu"]
    assert by_number[2]["status"] == "empty" and by_number[2]["group_id"] is None
