"""Covers the student "My Assignments" page: every assignment their own
group(s) have completed with their personal average confidence rating
(server/services/serializers.py:build_my_assignments), and the read-only
"View work" replay of their group's submitted code
(build_group_work) — see server/blueprints/sections.py:my_assignments and
server/blueprints/groups.py:get_group_work.
"""

from server.extensions import db
from server.models.group import Group, GroupAssignmentProgress, GroupMembership
from server.models.klass import Class
from server.models.rating import Rating
from server.models.section import Section
from server.models.test_run import TestRun
from server.models.user import User
from server.models.worksheet import Question, Worksheet
from server.tests.conftest import login_as


def _make_completed_assignment():
    klass = Class(course_name="C")
    db.session.add(klass)
    db.session.flush()
    section = Section(class_id=klass.id, name="S")
    db.session.add(section)
    db.session.flush()

    worksheet = Worksheet(class_id=klass.id, slug="w1", title="Disc 1", is_published=True)
    db.session.add(worksheet)
    db.session.flush()
    q1 = Question(worksheet_id=worksheet.id, order_index=0, title="Q1", prompt="p1")
    q2 = Question(worksheet_id=worksheet.id, order_index=1, title="Q2", prompt="p2")
    db.session.add_all([q1, q2])
    db.session.flush()

    student = User(display_name="Student", role="student")
    other_member = User(display_name="Teammate", role="student")
    db.session.add_all([student, other_member])
    db.session.flush()

    group = Group(section_id=section.id, number=1, name="G1")
    db.session.add(group)
    db.session.flush()
    db.session.add(GroupMembership(group_id=group.id, user_id=student.id))
    db.session.add(GroupMembership(group_id=group.id, user_id=other_member.id))
    # current_question_index == total question count means "completed".
    db.session.add(GroupAssignmentProgress(group_id=group.id, worksheet_id=worksheet.id, current_question_index=2))
    db.session.add(Rating(group_id=group.id, question_id=q1.id, user_id=student.id, value=4))
    db.session.add(Rating(group_id=group.id, question_id=q2.id, user_id=student.id, value=2))
    # A teammate's rating shouldn't affect the student's own average.
    db.session.add(Rating(group_id=group.id, question_id=q1.id, user_id=other_member.id, value=1))
    db.session.add(
        TestRun(
            group_id=group.id,
            question_id=q1.id,
            user_id=student.id,
            source="shared",
            prediction_text="x",
            code_snapshot="def f(): return 1",
            status="done",
            passed_count=1,
            total_count=1,
            results_json="{}",
        )
    )
    db.session.commit()
    return klass, section, worksheet, group, student, other_member


def test_my_assignments_only_lists_completed_ones(app, client, db):
    klass, section, worksheet, group, student, _other = _make_completed_assignment()

    # A second, not-yet-completed worksheet in the same class shouldn't show up.
    other_worksheet = Worksheet(class_id=klass.id, slug="w2", title="Disc 2", is_published=True)
    db.session.add(other_worksheet)
    db.session.flush()
    db.session.add(Question(worksheet_id=other_worksheet.id, order_index=0, title="Q1", prompt="p"))
    db.session.add(
        GroupAssignmentProgress(group_id=group.id, worksheet_id=other_worksheet.id, current_question_index=0)
    )
    db.session.commit()

    login_as(client, student)
    resp = client.get("/api/me/assignments")
    assert resp.status_code == 200
    assignments = resp.get_json()["assignments"]
    assert len(assignments) == 1
    assert assignments[0]["title"] == "Disc 1"
    assert assignments[0]["worksheet_id"] == worksheet.id
    assert assignments[0]["group_id"] == group.id


def test_my_assignments_averages_only_my_own_ratings(app, client, db):
    _klass, _section, _worksheet, _group, student, other_member = _make_completed_assignment()

    login_as(client, student)
    resp = client.get("/api/me/assignments")
    assert resp.get_json()["assignments"][0]["my_average_rating"] == 3.0  # (4 + 2) / 2, not the teammate's 1

    login_as(client, other_member)
    resp = client.get("/api/me/assignments")
    assert resp.get_json()["assignments"][0]["my_average_rating"] == 1.0


def test_get_group_work_shows_submitted_code_and_pass_state(app, client, db):
    _klass, _section, worksheet, group, student, _other = _make_completed_assignment()
    outsider = User(display_name="Outsider", role="student")
    db.session.add(outsider)
    db.session.commit()

    login_as(client, student)
    resp = client.get(f"/api/groups/{group.id}/worksheets/{worksheet.id}/work")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["worksheet_title"] == "Disc 1"
    by_title = {q["title"]: q for q in body["questions"]}
    assert by_title["Q1"]["code"] == "def f(): return 1"
    assert by_title["Q1"]["passed"] is True
    assert by_title["Q2"]["code"] is None  # never run

    login_as(client, outsider)
    resp = client.get(f"/api/groups/{group.id}/worksheets/{worksheet.id}/work")
    assert resp.status_code == 403
