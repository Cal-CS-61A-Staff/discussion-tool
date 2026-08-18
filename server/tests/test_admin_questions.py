"""Covers the assignment-management endpoints added for the Problem Sets
table / question editor: reordering, deleting a question (renumbering the
rest), and per-group grade aggregation. These are pure DB-logic routes (no
sandboxed grader involved), unlike create/update question which are already
exercised against the real Docker image in test_grading.py.
"""

import json

from server.extensions import db
from server.models.group import Group
from server.models.section import Section
from server.models.test_run import TestRun
from server.models.user import User
from server.models.worksheet import Question, Worksheet
from server.tests.conftest import login_as


def _make_section_with_questions(n=3):
    section = Section(course_name="C", name="S")
    db.session.add(section)
    db.session.flush()

    worksheet = Worksheet(section_id=section.id, slug="w1", title="W1")
    db.session.add(worksheet)
    db.session.flush()

    questions = []
    for i in range(n):
        q = Question(worksheet_id=worksheet.id, order_index=i, title=f"Q{i}", prompt="p")
        db.session.add(q)
        questions.append(q)

    ta = User(display_name="ta", role="ta")
    db.session.add(ta)
    db.session.commit()

    return section, worksheet, questions, ta


def test_reorder_questions_persists_new_order(app, client):
    _section, worksheet, questions, ta = _make_section_with_questions(3)
    login_as(client, ta)

    reversed_ids = [q.id for q in reversed(questions)]
    resp = client.put(f"/api/worksheets/{worksheet.id}/questions/reorder", json={"order": reversed_ids})
    assert resp.status_code == 200

    reloaded = Question.query.filter_by(worksheet_id=worksheet.id).order_by(Question.order_index).all()
    assert [q.id for q in reloaded] == reversed_ids


def test_reorder_rejects_mismatched_id_set(app, client):
    _section, worksheet, questions, ta = _make_section_with_questions(3)
    login_as(client, ta)

    bad_order = [questions[0].id, questions[1].id]  # missing questions[2]
    resp = client.put(f"/api/worksheets/{worksheet.id}/questions/reorder", json={"order": bad_order})
    assert resp.status_code == 400

    unchanged = Question.query.filter_by(worksheet_id=worksheet.id).order_by(Question.order_index).all()
    assert [q.id for q in unchanged] == [q.id for q in questions]


def test_delete_question_renumbers_remaining(app, client):
    _section, worksheet, questions, ta = _make_section_with_questions(3)
    login_as(client, ta)

    middle_id = questions[1].id
    resp = client.delete(f"/api/questions/{middle_id}")
    assert resp.status_code == 200

    remaining = Question.query.filter_by(worksheet_id=worksheet.id).order_by(Question.order_index).all()
    assert [q.id for q in remaining] == [questions[0].id, questions[2].id]
    assert [q.order_index for q in remaining] == [0, 1]


def test_worksheet_grades_aggregates_latest_run_per_question(app, client):
    section, worksheet, questions, ta = _make_section_with_questions(2)
    login_as(client, ta)

    group = Group(section_id=section.id, number=1, name="G1")
    db.session.add(group)
    student = User(display_name="s1", role="student")
    db.session.add(student)
    db.session.commit()

    # An older, worse run followed by a better one on question 0 — grades
    # should reflect the latest, not the max or the first.
    for total_points, max_points in [(0, 2), (2, 2)]:
        db.session.add(
            TestRun(
                group_id=group.id,
                question_id=questions[0].id,
                user_id=student.id,
                source="shared",
                prediction_text="x",
                code_snapshot="code",
                passed_count=int(total_points),
                total_count=2,
                total_points=total_points,
                max_points=max_points,
                results_json=json.dumps({}),
            )
        )
    db.session.commit()

    resp = client.get(f"/api/worksheets/{worksheet.id}/grades")
    assert resp.status_code == 200
    data = resp.get_json()["groups"]
    assert len(data) == 1
    row = data[0]
    assert row["group_id"] == group.id
    assert row["points_earned"] == 2
    assert row["points_possible"] == 2
    assert row["questions_attempted"] == 1
    assert row["total_questions"] == 2


def test_delete_worksheet_cascades(app, client):
    section, worksheet, questions, ta = _make_section_with_questions(1)
    login_as(client, ta)
    worksheet_id = worksheet.id
    question_id = questions[0].id

    group = Group(section_id=section.id, number=1, name="G1")
    db.session.add(group)
    student = User(display_name="s1", role="student")
    db.session.add(student)
    db.session.commit()
    db.session.add(
        TestRun(
            group_id=group.id,
            question_id=question_id,
            user_id=student.id,
            source="shared",
            prediction_text="x",
            code_snapshot="code",
            passed_count=1,
            total_count=1,
            total_points=1,
            max_points=1,
            results_json=json.dumps({}),
        )
    )
    db.session.commit()

    resp = client.delete(f"/api/worksheets/{worksheet_id}")
    assert resp.status_code == 200
    assert db.session.get(Worksheet, worksheet_id) is None
    assert Question.query.filter_by(worksheet_id=worksheet_id).count() == 0
    assert TestRun.query.filter_by(question_id=question_id).count() == 0
