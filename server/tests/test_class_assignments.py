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
from server.tests.conftest import (
    act_as_participant,
    add_member,
    join_worksheet,
    login_as,
    make_class,
    new_browser,
    publish,
)


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


def test_work_individually_reuses_one_solo_group(app, client, db):
    klass, _staff, _other, _outsider, _admin = _make_class()
    worksheet = Worksheet(class_id=klass.id, slug="w1", title="Disc 1")
    db.session.add(worksheet)
    db.session.flush()
    code = publish(worksheet)
    db.session.commit()

    resp = client.post(f"/api/w/{code}/work-individually", json={"name": "Solo"})
    assert resp.status_code == 200
    group_id = resp.get_json()["group_id"]

    resp2 = client.post(f"/api/w/{code}/work-individually", json={"name": "Solo"})
    assert resp2.get_json()["group_id"] == group_id
    assert Group.query.get(group_id).is_individual is True


def test_worksheet_grades_excludes_a_staff_preview_group(app, client, db):
    klass, staff, _other, _outsider, _admin = _make_class()

    login_as(client, staff)
    worksheet_id = client.post(f"/api/classes/{klass.id}/worksheets", json={"title": "Disc"}).get_json()["worksheet"]["id"]
    worksheet = db.session.get(Worksheet, worksheet_id)
    code = publish(worksheet)
    db.session.commit()

    # Staff previewing via the share link get a "staff-" participant key.
    staff_group_id = client.post(f"/api/w/{code}/work-individually", json={"name": "TA"}).get_json()["group_id"]

    # A real student, no account, fresh session.
    new_browser(client)
    student_group_id = client.post(
        f"/api/w/{code}/work-individually", json={"name": "Student"}
    ).get_json()["group_id"]

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


def test_join_by_number_creates_one_shared_group(app, client, db):
    klass, _staff, _other, _outsider, _admin = _make_class()
    worksheet = Worksheet(class_id=klass.id, slug="w1", title="Disc 1")
    db.session.add(worksheet)
    db.session.flush()
    code = publish(worksheet)
    db.session.commit()

    resp = client.post(f"/api/w/{code}/join", json={"name": "A", "number": 7})
    assert resp.status_code == 200
    group_id = resp.get_json()["group_id"]

    # a second, fresh browser on the same number lands in the same group
    new_browser(client)
    resp = client.post(f"/api/w/{code}/join", json={"name": "B", "number": 7})
    assert resp.get_json()["group_id"] == group_id

    assert Group.query.filter_by(class_id=klass.id, number=7, is_individual=False).count() == 1
    assert GroupMembership.query.filter_by(group_id=group_id).count() == 2

    # any member can rename the group; a non-member (fresh session) can't
    resp = client.put(f"/api/groups/{group_id}/name", json={"name": "Sea Otters"})
    assert resp.status_code == 200
    assert db.session.get(Group, group_id).name == "Sea Otters"

    new_browser(client)
    assert client.put(f"/api/groups/{group_id}/name", json={"name": "hax"}).status_code == 401


def test_join_requires_a_valid_share_code(app, client, db):
    _klass, *_rest = _make_class()
    assert client.post("/api/w/NOPE0000/join", json={"name": "X", "number": 1}).status_code == 404


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
    g1 = Group(class_id=klass.id, number=1, name="Group 1")
    db.session.add(g1)
    db.session.flush()
    db.session.add(GroupMembership(group_id=g1.id, participant_key="p-stu", participant_name="Stu"))
    db.session.commit()

    from server.tests.conftest import set_participant

    set_participant(client, "p-stu", "Stu")
    client.get(f"/api/groups/{g1.id}/state?worksheet_id={worksheet.id}")  # mark present

    login_as(client, staff)
    tiles = client.get(f"/api/worksheets/{worksheet.id}/dashboard").get_json()["groups"]
    by_number = {t["number"]: t for t in tiles}
    assert set(by_number) == {1, 2}
    assert by_number[1]["present"] == ["Stu"]
    assert by_number[2]["status"] == "empty" and by_number[2]["group_id"] is None
