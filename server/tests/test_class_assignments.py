"""Covers the actual point of the Class/Section split: assignments belong
to a Class and are shared across every Section under it, and any TA who
owns/co-teaches *any* section of that class (not just one specific section)
can author them — see server/auth.py:ta_owns_class and the worksheet/
question endpoints in server/blueprints/admin.py.
"""

from server.extensions import db
from server.models.group import Group, GroupAssignmentProgress, GroupMembership
from server.models.klass import Class
from server.models.rating import Rating
from server.models.section import Section
from server.models.user import User
from server.models.worksheet import Question, Worksheet
from server.tests.conftest import login_as


def _make_class_with_two_sections():
    ta_a = User(display_name="TA A", role="ta")
    ta_b = User(display_name="TA B", role="ta")
    outsider_ta = User(display_name="Outsider TA", role="ta")
    admin = User(display_name="Admin", role="admin")
    db.session.add_all([ta_a, ta_b, outsider_ta, admin])
    db.session.flush()

    klass = Class(course_name="CS 61A")
    db.session.add(klass)
    db.session.flush()

    section_a = Section(class_id=klass.id, name="Section A", ta_user_id=ta_a.id)
    section_b = Section(class_id=klass.id, name="Section B", ta_user_id=ta_b.id)
    db.session.add_all([section_a, section_b])
    db.session.commit()
    return klass, section_a, section_b, ta_a, ta_b, outsider_ta, admin


def test_either_sections_ta_can_create_an_assignment_for_the_class(app, client, db):
    klass, _a, _b, ta_a, ta_b, outsider_ta, admin = _make_class_with_two_sections()

    login_as(client, outsider_ta)
    resp = client.post(f"/api/classes/{klass.id}/worksheets", json={"title": "Disc 1"})
    assert resp.status_code == 403

    login_as(client, ta_a)
    resp = client.post(f"/api/classes/{klass.id}/worksheets", json={"title": "Disc 1"})
    assert resp.status_code == 201
    worksheet_id = resp.get_json()["worksheet"]["id"]

    # TA B doesn't own section A, but co-teaches the same *class* via
    # section B -- they can edit the assignment section A's TA authored.
    login_as(client, ta_b)
    resp = client.put(f"/api/worksheets/{worksheet_id}", json={"title": "Disc 1 (edited)"})
    assert resp.status_code == 200
    assert resp.get_json()["worksheet"]["title"] == "Disc 1 (edited)"

    login_as(client, admin)
    resp = client.post(f"/api/worksheets/{worksheet_id}/publish")
    assert resp.status_code == 200


def test_both_sections_see_the_same_published_assignment(app, client, db):
    klass, section_a, section_b, ta_a, _ta_b, _outsider, _admin = _make_class_with_two_sections()

    login_as(client, ta_a)
    resp = client.post(f"/api/classes/{klass.id}/worksheets", json={"title": "Shared Disc"})
    worksheet_id = resp.get_json()["worksheet"]["id"]
    client.post(f"/api/worksheets/{worksheet_id}/publish")

    student = User(display_name="Student", role="student")
    db.session.add(student)
    db.session.commit()
    login_as(client, student)

    resp = client.get(f"/api/sections/{section_a.id}/worksheets")
    assert [w["title"] for w in resp.get_json()["worksheets"]] == ["Shared Disc"]

    resp = client.get(f"/api/sections/{section_b.id}/worksheets")
    assert [w["title"] for w in resp.get_json()["worksheets"]] == ["Shared Disc"]


def test_worksheet_grades_span_every_section_of_the_class(app, client, db):
    klass, section_a, section_b, ta_a, _ta_b, _outsider, _admin = _make_class_with_two_sections()

    login_as(client, ta_a)
    resp = client.post(f"/api/classes/{klass.id}/worksheets", json={"title": "Disc"})
    worksheet_id = resp.get_json()["worksheet"]["id"]

    group_a = Group(section_id=section_a.id, number=1, name="Group A1")
    group_b = Group(section_id=section_b.id, number=1, name="Group B1")
    db.session.add_all([group_a, group_b])
    db.session.commit()

    resp = client.get(f"/api/worksheets/{worksheet_id}/grades")
    assert resp.status_code == 200
    group_ids = {row["group_id"] for row in resp.get_json()["groups"]}
    assert group_ids == {group_a.id, group_b.id}


def test_ta_can_work_individually_on_a_section_they_own(app, client, db):
    """Backs "View as student" on the Assignments page — a TA gets the
    same solo-group flow a student would, to sanity-check an assignment.
    """
    _klass, section_a, _section_b, ta_a, _ta_b, outsider_ta, admin = _make_class_with_two_sections()

    login_as(client, ta_a)
    resp = client.post(f"/api/sections/{section_a.id}/work-individually")
    assert resp.status_code == 200
    group = resp.get_json()["group"]
    assert group["is_individual"] is True

    # Calling it again reuses the same group rather than making a new one.
    resp2 = client.post(f"/api/sections/{section_a.id}/work-individually")
    assert resp2.get_json()["group"]["id"] == group["id"]

    login_as(client, outsider_ta)
    resp = client.post(f"/api/sections/{section_a.id}/work-individually")
    assert resp.status_code == 403

    login_as(client, admin)
    resp = client.post(f"/api/sections/{section_a.id}/work-individually")
    assert resp.status_code == 200


def test_worksheet_grades_excludes_a_tas_own_preview_group(app, client, db):
    klass, section_a, _section_b, ta_a, _ta_b, _outsider, _admin = _make_class_with_two_sections()

    login_as(client, ta_a)
    resp = client.post(f"/api/classes/{klass.id}/worksheets", json={"title": "Disc"})
    worksheet_id = resp.get_json()["worksheet"]["id"]

    resp = client.post(f"/api/sections/{section_a.id}/work-individually")
    ta_group_id = resp.get_json()["group"]["id"]

    student = User(display_name="Student", role="student")
    db.session.add(student)
    db.session.commit()
    login_as(client, student)
    resp = client.post(f"/api/sections/{section_a.id}/work-individually")
    student_group_id = resp.get_json()["group"]["id"]

    login_as(client, ta_a)
    resp = client.get(f"/api/worksheets/{worksheet_id}/grades")
    assert resp.status_code == 200
    group_ids = {row["group_id"] for row in resp.get_json()["groups"]}
    assert student_group_id in group_ids
    assert ta_group_id not in group_ids


def test_dashboard_only_shows_groups_from_sections_the_ta_owns(app, client, db):
    klass, section_a, section_b, ta_a, ta_b, _outsider, admin = _make_class_with_two_sections()

    login_as(client, ta_a)
    resp = client.post(f"/api/classes/{klass.id}/worksheets", json={"title": "Disc"})
    worksheet_id = resp.get_json()["worksheet"]["id"]

    group_a = Group(section_id=section_a.id, number=1, name="Group A1")
    group_b = Group(section_id=section_b.id, number=1, name="Group B1")
    db.session.add_all([group_a, group_b])
    db.session.commit()

    # TA A co-owns the class's assignment content, but only manages section
    # A's live groups -- not section B's, even though it's the same class.
    login_as(client, ta_a)
    resp = client.get(f"/api/worksheets/{worksheet_id}/dashboard")
    assert resp.status_code == 200
    names = {g["name"] for g in resp.get_json()["groups"]}
    assert names == {"Group A1"}

    login_as(client, ta_b)
    resp = client.get(f"/api/worksheets/{worksheet_id}/dashboard")
    names = {g["name"] for g in resp.get_json()["groups"]}
    assert names == {"Group B1"}

    login_as(client, admin)
    resp = client.get(f"/api/worksheets/{worksheet_id}/dashboard")
    names = {g["name"] for g in resp.get_json()["groups"]}
    assert names == {"Group A1", "Group B1"}


def test_question_endpoints_use_class_level_access_too(app, client, db):
    klass, _a, _b, ta_a, ta_b, outsider_ta, _admin = _make_class_with_two_sections()

    login_as(client, ta_a)
    resp = client.post(f"/api/classes/{klass.id}/worksheets", json={"title": "Disc"})
    worksheet_id = resp.get_json()["worksheet"]["id"]

    login_as(client, outsider_ta)
    resp = client.get(f"/api/worksheets/{worksheet_id}/questions")
    assert resp.status_code == 403

    login_as(client, ta_b)
    resp = client.get(f"/api/worksheets/{worksheet_id}/questions")
    assert resp.status_code == 200


def test_class_worksheets_endpoint_lists_by_class_directly(app, client, db):
    klass, _a, _b, ta_a, _ta_b, outsider_ta, _admin = _make_class_with_two_sections()

    login_as(client, ta_a)
    client.post(f"/api/classes/{klass.id}/worksheets", json={"title": "Draft"})
    resp = client.post(f"/api/classes/{klass.id}/worksheets", json={"title": "Published"})
    client.post(f"/api/worksheets/{resp.get_json()['worksheet']['id']}/publish")

    resp = client.get(f"/api/classes/{klass.id}/worksheets")
    assert {w["title"] for w in resp.get_json()["worksheets"]} == {"Draft", "Published"}

    login_as(client, outsider_ta)
    resp = client.get(f"/api/classes/{klass.id}/worksheets")
    assert {w["title"] for w in resp.get_json()["worksheets"]} == {"Published"}


def test_section_progress_shows_roster_and_completion(app, client, db):
    klass, section_a, section_b, ta_a, ta_b, outsider_ta, _admin = _make_class_with_two_sections()

    login_as(client, ta_a)
    resp = client.post(f"/api/classes/{klass.id}/worksheets", json={"title": "Disc"})
    worksheet_id = resp.get_json()["worksheet"]["id"]
    client.post(f"/api/worksheets/{worksheet_id}/publish")

    group = Group(section_id=section_a.id, number=1, name="Group A1")
    student = User(display_name="Student", role="student")
    db.session.add_all([group, student])
    db.session.flush()
    from server.models.group import GroupAssignmentProgress, GroupMembership

    db.session.add(GroupMembership(group_id=group.id, user_id=student.id))
    db.session.add(GroupAssignmentProgress(group_id=group.id, worksheet_id=worksheet_id, current_question_index=0))
    db.session.commit()

    resp = client.get(f"/api/sections/{section_a.id}/progress")
    assert resp.status_code == 200
    rows = resp.get_json()["groups"]
    assert len(rows) == 1
    assert rows[0]["member_names"] == ["Student"]
    assert rows[0]["total_assignments"] == 1

    login_as(client, ta_b)
    resp = client.get(f"/api/sections/{section_a.id}/progress")
    assert resp.status_code == 403

    login_as(client, outsider_ta)
    resp = client.get(f"/api/sections/{section_a.id}/progress")
    assert resp.status_code == 403


def test_list_classes_scoped_like_sections(app, client, db):
    klass, _a, _b, ta_a, _ta_b, outsider_ta, admin = _make_class_with_two_sections()

    login_as(client, ta_a)
    resp = client.get("/api/classes")
    assert {c["id"] for c in resp.get_json()["classes"]} == {klass.id}

    login_as(client, outsider_ta)
    resp = client.get("/api/classes")
    assert resp.get_json()["classes"] == []

    login_as(client, admin)
    resp = client.get("/api/classes")
    assert {c["id"] for c in resp.get_json()["classes"]} == {klass.id}


def test_only_an_admin_can_create_a_class(app, client, db):
    """POST /classes is admin-only, unlike every other staff action in this
    app (creating/editing assignments, managing groups) which is
    TA-or-admin — creating a brand new course, role assignment, and
    archiving are the only things reserved for admins specifically.
    """
    ta = User(display_name="TA", role="ta")
    student = User(display_name="Student", role="student")
    admin = User(display_name="Admin", role="admin")
    db.session.add_all([ta, student, admin])
    db.session.commit()

    login_as(client, ta)
    resp = client.post("/api/classes", json={"course_name": "CS 61B"})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "You do not have permission to create a new class."

    login_as(client, student)
    resp = client.post("/api/classes", json={"course_name": "CS 61C"})
    assert resp.status_code == 403

    login_as(client, admin)
    resp = client.post("/api/classes", json={"course_name": "CS 61D"})
    assert resp.status_code == 201
    assert resp.get_json()["klass"]["is_archived"] is False


def test_only_an_admin_can_archive_a_class(app, client, db):
    """Admin-only, and deliberately not scoped by ta_owns_class/
    require_class_access at all -- even the class's own owning TA can't
    archive it, same as they can't create one."""
    klass, _a, _b, ta_a, _ta_b, outsider_ta, admin = _make_class_with_two_sections()

    login_as(client, outsider_ta)
    resp = client.put(f"/api/classes/{klass.id}/archive", json={"is_archived": True})
    assert resp.status_code == 403

    login_as(client, ta_a)
    resp = client.put(f"/api/classes/{klass.id}/archive", json={"is_archived": True})
    assert resp.status_code == 403

    login_as(client, admin)
    resp = client.put(f"/api/classes/{klass.id}/archive", json={"is_archived": True})
    assert resp.status_code == 200
    assert resp.get_json()["klass"]["is_archived"] is True

    resp = client.put(f"/api/classes/{klass.id}/archive", json={"is_archived": False})
    assert resp.status_code == 200
    assert resp.get_json()["klass"]["is_archived"] is False


def test_class_worksheets_includes_a_students_own_rating(app, client, db):
    """The shared Assignments page's per-row rating (server/services/
    serializers.py:student_worksheet_progress) — null before the student's
    group has any progress on it, populated (and scoped to their own
    ratings, not a groupmate's) once they've started.
    """
    klass, section_a, _b, ta_a, _ta_b, _outsider_ta, _admin = _make_class_with_two_sections()
    worksheet = Worksheet(class_id=klass.id, slug="w1", title="Disc 1", is_published=True)
    db.session.add(worksheet)
    db.session.flush()
    question = Question(worksheet_id=worksheet.id, order_index=0, title="Q1", prompt="p")
    db.session.add(question)
    db.session.flush()

    student = User(display_name="Student", role="student")
    db.session.add(student)
    db.session.flush()
    group = Group(section_id=section_a.id, number=1, name="G1")
    db.session.add(group)
    db.session.flush()
    db.session.add(GroupMembership(group_id=group.id, user_id=student.id))
    db.session.commit()

    login_as(client, student)
    resp = client.get(f"/api/classes/{klass.id}/worksheets")
    worksheet_payload = resp.get_json()["worksheets"][0]
    assert worksheet_payload["my_rating"] is None
    assert worksheet_payload["my_group_id"] is None

    db.session.add(GroupAssignmentProgress(group_id=group.id, worksheet_id=worksheet.id, current_question_index=0))
    db.session.add(Rating(group_id=group.id, question_id=question.id, user_id=student.id, value=5))
    db.session.commit()

    resp = client.get(f"/api/classes/{klass.id}/worksheets")
    worksheet_payload = resp.get_json()["worksheets"][0]
    assert worksheet_payload["my_rating"] == 5.0
    assert worksheet_payload["my_group_id"] == group.id

    # A TA who isn't personally a member of any group here just gets null
    # back for both fields -- the frontend only renders them for students
    # anyway, since staff rows show the edit/publish actions instead.
    login_as(client, ta_a)
    resp = client.get(f"/api/classes/{klass.id}/worksheets")
    worksheet_payload = resp.get_json()["worksheets"][0]
    assert worksheet_payload["my_rating"] is None
    assert worksheet_payload["my_group_id"] is None
