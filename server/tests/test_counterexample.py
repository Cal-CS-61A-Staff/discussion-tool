"""Integration tests for the 'counterexample' problem type — grades a
student's chosen inputs by running the buggy code vs a correct reference in
the real grader sandbox. Requires the discussion-grader Docker image, like
test_grading.py.
"""

import shutil

import pytest

from server.extensions import db
from server.models.group import Group, GroupAssignmentProgress, GroupMembership
from server.models.klass import Class
from server.models.section import Section
from server.models.user import User
from server.models.worksheet import Question, Worksheet
from server.services import counterexample_grading
from server.services import response_grading
from server.tests.conftest import login_as

pytestmark = pytest.mark.skipif(shutil.which("docker") is None, reason="docker not available")

# race(x, y): the D1 bug — the loop condition `tortoise - hare` can skip
# past 0 (they cross without landing exactly equal), so it runs forever.
BUGGY = """
def race(x, y):
    tortoise, hare, minutes = 0, 0, 0
    while (minutes == 0) or (tortoise - hare):
        tortoise += x
        if minutes % 10 < 5:
            hare += y
        minutes += 1
    return minutes
"""

REFERENCE = """
def race(x, y):
    tortoise, hare, minutes = 0, 0, 0
    while minutes == 0 or tortoise < hare:
        tortoise += x
        if minutes % 10 < 5:
            hare += y
        minutes += 1
    return minutes
"""

CONTENT = {
    "params": [{"name": "x"}, {"name": "y"}],
    "call": "race(x, y)",
    "buggy_code": BUGGY,
    "reference_code": REFERENCE,
    "constraints": "y > x and y <= 2 * x",
}


def _question():
    clean, err = response_grading.validate_content("counterexample", CONTENT)
    assert err is None, err
    import json

    return Question(problem_type="counterexample", grading_mode="discussion", content_json=json.dumps(clean),
                    prompt="p", title="Race", order_index=0)


def test_grade_flags_a_constraint_violation(app):
    q = _question()
    ok, err = counterexample_grading.grade(q, {"x": "7", "y": "5"})  # y < x
    assert ok is None and "constraint" in err


def test_grade_rejects_non_literal_input(app):
    q = _question()
    ok, err = counterexample_grading.grade(q, {"x": "__import__('os')", "y": "5"})
    assert ok is None and err


def test_grade_accepts_a_pair_that_makes_the_buggy_code_loop(app):
    q = _question()
    # x=2, y=3: hare pulls ahead then the tortoise overshoots -> infinite loop.
    ok, err = counterexample_grading.grade(q, {"x": "2", "y": "3"})
    assert err is None
    assert ok is True


def test_grade_rejects_a_pair_the_buggy_code_handles(app):
    q = _question()
    ok, err = counterexample_grading.grade(q, {"x": "5", "y": "10"})  # exactly 2x — they meet cleanly
    assert err is None
    assert ok is False


def test_submit_response_endpoint_grades_in_the_sandbox(app, client):
    ta = User(display_name="ta", role="ta")
    student = User(display_name="s", role="student")
    db.session.add_all([ta, student])
    db.session.flush()
    klass = Class(course_name="C")
    db.session.add(klass)
    db.session.flush()
    section = Section(class_id=klass.id, name="S", ta_user_id=ta.id)
    db.session.add(section)
    db.session.flush()
    ws = Worksheet(class_id=klass.id, slug="w", title="W", is_published=True)
    db.session.add(ws)
    db.session.flush()
    q = _question()
    q.worksheet_id = ws.id
    db.session.add(q)
    group = Group(section_id=section.id, number=1, name="G")
    db.session.add(group)
    db.session.flush()
    db.session.add(GroupMembership(group_id=group.id, user_id=student.id))
    db.session.add(GroupAssignmentProgress(group_id=group.id, worksheet_id=ws.id, current_question_index=0))
    db.session.commit()

    login_as(client, student)
    resp = client.post(
        f"/api/groups/{group.id}/worksheets/{ws.id}/questions/{q.id}/response",
        json={"response": {"x": "2", "y": "3"}},
    )
    assert resp.status_code == 200
    assert resp.get_json()["is_correct"] is True
