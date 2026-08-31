"""Non-code problem types (Question.problem_type != 'coding'): authoring
validation, answer-stripped student payload, shared-group-answer grading,
and advancement gating.
"""

import json

from server.extensions import db
from server.models.group import Group, GroupAssignmentProgress, GroupMembership
from server.models.klass import Class
from server.models.question_response import QuestionResponse
from server.models.rating import Rating
from server.models.section import Section
from server.models.user import User
from server.models.worksheet import Question, Worksheet
from server.services import advance as advance_service
from server.services import response_grading
from server.tests.conftest import login_as


def _setup():
    ta = User(display_name="ta", role="ta")
    db.session.add(ta)
    db.session.flush()

    klass = Class(course_name="C")
    db.session.add(klass)
    db.session.flush()

    section = Section(class_id=klass.id, name="S", ta_user_id=ta.id)
    db.session.add(section)
    db.session.flush()

    worksheet = Worksheet(class_id=klass.id, slug="w1", title="W1", is_published=True)
    db.session.add(worksheet)
    db.session.flush()

    group = Group(section_id=section.id, number=1, name="G1")
    db.session.add(group)
    student = User(display_name="s1", role="student")
    db.session.add(student)
    db.session.flush()

    db.session.add(GroupMembership(group_id=group.id, user_id=student.id))
    db.session.add(GroupAssignmentProgress(group_id=group.id, worksheet_id=worksheet.id, current_question_index=0))
    db.session.commit()
    return {"ta": ta, "worksheet": worksheet, "group": group, "student": student}


def _create(client, worksheet_id, payload):
    return client.post(f"/api/worksheets/{worksheet_id}/questions", json=payload)


MC_PAYLOAD = {
    "title": "Pick one",
    "prompt": "Which?",
    "problem_type": "multiple_choice",
    "content": {
        "options": [
            {"text": "a", "correct": False},
            {"text": "b", "correct": True},
            {"text": "c", "correct": False},
        ]
    },
}


def test_create_each_non_code_type_persists(app, client):
    s = _setup()
    login_as(client, s["ta"])
    wid = s["worksheet"].id

    cases = [
        MC_PAYLOAD,
        {
            "title": "Dropdown",
            "prompt": "p",
            "problem_type": "dropdown",
            "content": {"options": [{"text": "x", "correct": True}, {"text": "y", "correct": False}]},
        },
        {
            "title": "Blanks",
            "prompt": "p",
            "problem_type": "fill_blank_code",
            "content": {
                "template": "def f(): return [[1]] + [[2]]",
                "blanks": [{"answer": "1"}, {"answer": "2", "accept": ["two"]}],
            },
        },
        {
            "title": "Short",
            "prompt": "p",
            "problem_type": "short_answer",
            "content": {"answer": "O(n)", "accept": ["linear"]},
        },
        {"title": "Md", "prompt": "p", "problem_type": "text_markdown", "content": {}},
        {"title": "Free", "prompt": "p", "problem_type": "plain_text", "content": {"min_length": 10}},
        {"title": "Img", "prompt": "p", "problem_type": "image", "content": {"url": "http://x/y.png", "alt": "y"}},
        {"title": "Frame", "prompt": "p", "problem_type": "iframe", "content": {"url": "http://x", "height": 300}},
    ]
    for payload in cases:
        resp = _create(client, wid, payload)
        assert resp.status_code == 201, (payload["problem_type"], resp.get_json())
        q = resp.get_json()["question"]
        assert q["problem_type"] == payload["problem_type"]
        assert q["content"] is not None

    assert Question.query.filter_by(worksheet_id=wid).count() == len(cases)


def test_authoring_validation_rejects_bad_content(app, client):
    s = _setup()
    login_as(client, s["ta"])
    wid = s["worksheet"].id

    bad = [
        {"title": "t", "prompt": "p", "problem_type": "multiple_choice", "content": {"options": [{"text": "only"}]}},
        {
            "title": "t",
            "prompt": "p",
            "problem_type": "dropdown",
            "content": {"options": [{"text": "a", "correct": True}, {"text": "b", "correct": True}]},
        },
        {"title": "t", "prompt": "p", "problem_type": "image", "content": {"alt": "no url"}},
        {
            "title": "t",
            "prompt": "p",
            "problem_type": "fill_blank_code",
            "content": {"template": "no markers here", "blanks": []},
        },
    ]
    for payload in bad:
        resp = _create(client, wid, payload)
        assert resp.status_code == 400, payload["problem_type"]


def test_student_state_strips_answers(app, client):
    s = _setup()
    login_as(client, s["ta"])
    wid = s["worksheet"].id
    _create(client, wid, MC_PAYLOAD)

    login_as(client, s["student"])
    resp = client.get(f"/api/groups/{s['group'].id}/state?worksheet_id={wid}")
    assert resp.status_code == 200
    question = resp.get_json()["question"]
    assert question["problem_type"] == "multiple_choice"
    assert question["content"]["options"] == [{"text": "a"}, {"text": "b"}, {"text": "c"}]
    assert "correct" not in json.dumps(question["content"])


def test_shared_response_grading_and_advance_gate(app, client):
    s = _setup()
    login_as(client, s["ta"])
    wid = s["worksheet"].id
    qid = _create(client, wid, MC_PAYLOAD).get_json()["question"]["id"]
    gid = s["group"].id

    login_as(client, s["student"])
    url = f"/api/groups/{gid}/worksheets/{wid}/questions/{qid}/response"

    wrong = client.post(url, json={"response": [0]})
    assert wrong.status_code == 200 and wrong.get_json()["is_correct"] is False

    # Everyone has rated, but the group answer is still wrong -> not ready.
    db.session.add(Rating(group_id=gid, question_id=qid, user_id=s["student"].id, value=3))
    db.session.commit()
    assert advance_service.ready_to_advance(gid, qid) is False

    right = client.post(url, json={"response": [1]})
    assert right.status_code == 200 and right.get_json()["is_correct"] is True

    row = QuestionResponse.query.filter_by(group_id=gid, question_id=qid).one()
    assert row.is_correct is True and json.loads(row.response_json) == [1]
    assert advance_service.ready_to_advance(gid, qid) is True


def test_display_type_advances_on_ratings_alone(app, client):
    s = _setup()
    login_as(client, s["ta"])
    wid = s["worksheet"].id
    qid = _create(
        client, wid, {"title": "read", "prompt": "just read this", "problem_type": "text_markdown", "content": {}}
    ).get_json()["question"]["id"]
    gid = s["group"].id

    assert advance_service.ready_to_advance(gid, qid) is False  # nobody rated yet
    db.session.add(Rating(group_id=gid, question_id=qid, user_id=s["student"].id, value=5))
    db.session.commit()
    assert advance_service.ready_to_advance(gid, qid) is True


def test_coding_question_ignores_response_endpoint(app, client):
    s = _setup()
    login_as(client, s["ta"])
    wid = s["worksheet"].id
    q = Question(worksheet_id=wid, order_index=0, title="code", prompt="p", problem_type="coding")
    db.session.add(q)
    db.session.commit()

    login_as(client, s["student"])
    resp = client.post(
        f"/api/groups/{s['group'].id}/worksheets/{wid}/questions/{q.id}/response", json={"response": "x"}
    )
    assert resp.status_code == 400


def test_worksheet_grades_count_a_correct_multiple_choice(app, client):
    s = _setup()
    login_as(client, s["ta"])
    wid = s["worksheet"].id
    qid = _create(client, wid, MC_PAYLOAD).get_json()["question"]["id"]
    gid = s["group"].id

    login_as(client, s["student"])
    client.post(f"/api/groups/{gid}/worksheets/{wid}/questions/{qid}/response", json={"response": [1]})

    login_as(client, s["ta"])
    resp = client.get(f"/api/worksheets/{wid}/grades")
    assert resp.status_code == 200
    row = next(r for r in resp.get_json()["groups"] if r["group_id"] == gid)
    assert row["questions_attempted"] == 1
    assert row["questions_passed"] == 1


# --- prediction questions -------------------------------------------------

DOCTEST_BLOCK = ">>> 1 + 1\n2\n>>> sorted([3, 1, 2])\n[1, 2, 3]\n"


def _make_prediction_question(worksheet_id, doctest_text=DOCTEST_BLOCK, setup=""):
    clean, err = response_grading.validate_content("prediction", {"setup": setup, "doctest": doctest_text})
    assert err is None, err
    q = Question(
        worksheet_id=worksheet_id,
        order_index=0,
        title="Predict",
        prompt="what prints?",
        problem_type="prediction",
        grading_mode="discussion",
        content_json=json.dumps(clean),
    )
    db.session.add(q)
    db.session.commit()
    return q


def test_parse_prediction_items_splits_a_doctest_block():
    items, err = response_grading.parse_prediction_items(DOCTEST_BLOCK)
    assert err is None
    assert items == [
        {"code": "1 + 1", "expected": "2"},
        {"code": "sorted([3, 1, 2])", "expected": "[1, 2, 3]"},
    ]
    _, err2 = response_grading.parse_prediction_items("no examples here")
    assert err2 is not None


def test_prediction_state_gives_one_item_without_the_answer(app, client):
    s = _setup()
    q = _make_prediction_question(s["worksheet"].id)

    login_as(client, s["student"])
    resp = client.get(f"/api/groups/{s['group'].id}/state?worksheet_id={s['worksheet'].id}")
    assert resp.status_code == 200
    content = resp.get_json()["question"]["content"]
    assert content["item_count"] == 2
    assert content["item"]["code"] in {"1 + 1", "sorted([3, 1, 2])"}
    assert "expected" not in json.dumps(content)


def test_prediction_grading_against_the_drawn_item(app, client):
    s = _setup()
    q = _make_prediction_question(s["worksheet"].id)
    gid, wid = s["group"].id, s["worksheet"].id

    login_as(client, s["student"])
    # Draw the item (as the live page would by polling /state).
    client.get(f"/api/groups/{gid}/state?worksheet_id={wid}")
    from server.services import serializers

    item = serializers.group_prediction_item(q, gid)
    assert item is not None

    url = f"/api/groups/{gid}/worksheets/{wid}/questions/{q.id}/response"
    wrong = client.post(url, json={"response": "definitely not it"})
    assert wrong.get_json()["is_correct"] is False

    db.session.add(Rating(group_id=gid, question_id=q.id, user_id=s["student"].id, value=4))
    db.session.commit()
    assert advance_service.ready_to_advance(gid, q.id) is False

    right = client.post(url, json={"response": item["expected"]})
    assert right.get_json()["is_correct"] is True
    assert advance_service.ready_to_advance(gid, q.id) is True


def test_prediction_output_match_is_whitespace_tolerant(app):
    assert response_grading.check_prediction("[1, 2, 3]", "  [1, 2, 3]  \n") is True
    assert response_grading.check_prediction("2", "3") is False
