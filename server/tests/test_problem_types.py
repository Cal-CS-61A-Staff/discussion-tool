"""Non-code problem types (Question.problem_type != 'coding'): authoring
validation, answer-stripped student payload, shared-group-answer grading,
and advancement gating.
"""

import json

from server.extensions import db
from server.models.group import Group, GroupAssignmentProgress, GroupMembership
from server.models.question_response import QuestionResponse
from server.models.rating import Rating
from server.models.user import User
from server.models.worksheet import Question, Worksheet
from server.services import advance as advance_service
from server.services import response_grading
from server.tests.conftest import act_as_participant, add_member, login_as, make_class


def _setup():
    ta = User(display_name="ta", role="student")
    db.session.add(ta)
    db.session.flush()

    klass = make_class("C")
    add_member(ta, klass, "staff")

    worksheet = Worksheet(class_id=klass.id, slug="w1", title="W1", is_published=True)
    db.session.add(worksheet)
    db.session.flush()

    group = Group(class_id=klass.id, number=1, name="G1")
    db.session.add(group)
    student = User(display_name="s1", role="student")
    db.session.add(student)
    db.session.flush()

    db.session.add(GroupMembership(group_id=group.id, participant_key=f"u{student.id}", participant_name=student.display_name))
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

    act_as_participant(client, s["student"])
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

    act_as_participant(client, s["student"])
    url = f"/api/groups/{gid}/worksheets/{wid}/questions/{qid}/response"

    wrong = client.post(url, json={"response": [0]})
    assert wrong.status_code == 200 and wrong.get_json()["is_correct"] is False

    # Everyone has rated, but the group answer is still wrong -> not ready.
    db.session.add(Rating(group_id=gid, question_id=qid, participant_key=f'u{s["student"].id}', value=3))
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
    db.session.add(Rating(group_id=gid, question_id=qid, participant_key=f'u{s["student"].id}', value=5))
    db.session.commit()
    assert advance_service.ready_to_advance(gid, qid) is True


def test_coding_question_ignores_response_endpoint(app, client):
    s = _setup()
    login_as(client, s["ta"])
    wid = s["worksheet"].id
    q = Question(worksheet_id=wid, order_index=0, title="code", prompt="p", problem_type="coding")
    db.session.add(q)
    db.session.commit()

    act_as_participant(client, s["student"])
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

    act_as_participant(client, s["student"])
    client.post(f"/api/groups/{gid}/worksheets/{wid}/questions/{qid}/response", json={"response": [1]})

    login_as(client, s["ta"])
    resp = client.get(f"/api/worksheets/{wid}/grades")
    assert resp.status_code == 200
    row = next(r for r in resp.get_json()["groups"] if r["group_id"] == gid)
    assert row["questions_attempted"] == 1
    assert row["questions_passed"] == 1


# --- the optional prediction prompt (any problem_type) -------------------

# The sandbox-resolved shape (server/blueprints/admin.py:_resolve_prediction_items
# does this at save time from a list of `calls`; tests build it directly
# since the grader Docker image isn't available here).
OUTPUT_PRED = {
    "mode": "output",
    "setup": "",
    "calls": ["1 + 1", "sorted([3, 1, 2])"],
    "items": [{"code": "1 + 1", "expected": "2"}, {"code": "sorted([3, 1, 2])", "expected": "[1, 2, 3]"}],
}


def _make_question(worksheet_id, prediction=None):
    q = Question(
        worksheet_id=worksheet_id,
        order_index=0,
        title="Q",
        prompt="a conceptual prompt",
        problem_type="coding",
        grading_mode="discussion",
        prediction_json=json.dumps(prediction) if prediction else None,
    )
    db.session.add(q)
    db.session.commit()
    return q


def test_validate_prediction_modes():
    # The editor resolves each call's output in the browser and sends `items`;
    # validate_prediction shape-checks that they line up with `calls`.
    ok_items = [{"code": "fizzbuzz(5)", "expected": "1\n2\nfizz"}, {"code": "fizzbuzz(15)", "expected": "..."}]
    clean, err = response_grading.validate_prediction(
        {"mode": "output", "calls": ["fizzbuzz(5)", "fizzbuzz(15)"], "items": ok_items}
    )
    assert err is None and clean["calls"] == ["fizzbuzz(5)", "fizzbuzz(15)"] and len(clean["items"]) == 2
    # calls can also arrive as a newline string from the editor textarea.
    clean, err = response_grading.validate_prediction(
        {"mode": "output", "calls": "fizzbuzz(5)\n\nfizzbuzz(15)\n", "items": ok_items}
    )
    assert err is None and clean["calls"] == ["fizzbuzz(5)", "fizzbuzz(15)"]
    # items missing / count mismatch -> rejected
    _, err = response_grading.validate_prediction({"mode": "output", "calls": ["fizzbuzz(5)"], "items": []})
    assert err is not None
    _, err = response_grading.validate_prediction({"mode": "output", "calls": [], "items": []})
    assert err is not None
    clean, err = response_grading.validate_prediction({"mode": "written", "prompt": "why?"})
    assert err is None and clean == {"mode": "written", "prompt": "why?"}
    _, err = response_grading.validate_prediction({"mode": "written", "prompt": ""})
    assert err is not None
    assert response_grading.validate_prediction(None) == (None, None)


def test_output_prediction_state_hides_the_answer(app, client):
    s = _setup()
    q = _make_question(s["worksheet"].id, OUTPUT_PRED)

    act_as_participant(client, s["student"])
    resp = client.get(f"/api/groups/{s['group'].id}/state?worksheet_id={s['worksheet'].id}")
    assert resp.status_code == 200
    pred = resp.get_json()["question"]["prediction"]
    assert pred["mode"] == "output"
    assert pred["item"]["code"] in {"1 + 1", "sorted([3, 1, 2])"}
    assert "expected" not in json.dumps(pred)


def test_output_prediction_gates_advancing(app, client):
    s = _setup()
    q = _make_question(s["worksheet"].id, OUTPUT_PRED)
    gid, wid = s["group"].id, s["worksheet"].id
    from server.services import serializers

    act_as_participant(client, s["student"])
    client.get(f"/api/groups/{gid}/state?worksheet_id={wid}")
    item = serializers.group_prediction_item(q, gid)
    db.session.add(Rating(group_id=gid, question_id=q.id, participant_key=f'u{s["student"].id}', value=4))
    db.session.commit()

    url = f"/api/groups/{gid}/worksheets/{wid}/questions/{q.id}/prediction"
    assert client.post(url, json={"text": "not it"}).get_json()["is_correct"] is False
    assert advance_service.ready_to_advance(gid, q.id) is False

    assert client.post(url, json={"text": item["expected"]}).get_json()["is_correct"] is True
    assert advance_service.ready_to_advance(gid, q.id) is True


def test_written_prediction_gates_until_submitted(app, client):
    s = _setup()
    q = _make_question(s["worksheet"].id, {"mode": "written", "prompt": "describe your process"})
    gid, wid = s["group"].id, s["worksheet"].id

    act_as_participant(client, s["student"])
    db.session.add(Rating(group_id=gid, question_id=q.id, participant_key=f'u{s["student"].id}', value=4))
    db.session.commit()
    assert advance_service.ready_to_advance(gid, q.id) is False

    resp = client.post(f"/api/groups/{gid}/worksheets/{wid}/questions/{q.id}/prediction", json={"text": "we did X"})
    assert resp.get_json()["is_correct"] is None
    assert advance_service.ready_to_advance(gid, q.id) is True


def test_no_prediction_means_no_gate(app, client):
    s = _setup()
    q = _make_question(s["worksheet"].id, prediction=None)
    gid = s["group"].id
    db.session.add(Rating(group_id=gid, question_id=q.id, participant_key=f'u{s["student"].id}', value=4))
    db.session.commit()
    assert advance_service.ready_to_advance(gid, q.id) is True


def test_prediction_output_match_is_whitespace_tolerant(app):
    assert response_grading.check_prediction("[1, 2, 3]", "  [1, 2, 3]  \n") is True
    assert response_grading.check_prediction("2", "3") is False


def test_python_tutor_code_round_trips(app, client):
    s = _setup()
    login_as(client, s["ta"])
    wid = s["worksheet"].id
    resp = client.post(
        f"/api/worksheets/{wid}/questions",
        json={"title": "diagram", "prompt": "step through", "problem_type": "text_markdown", "content": {},
              "python_tutor_code": "x = 1\ny = x + 1"},
    )
    assert resp.status_code == 201
    assert resp.get_json()["question"]["python_tutor_code"] == "x = 1\ny = x + 1"

    act_as_participant(client, s["student"])
    state = client.get(f"/api/groups/{s['group'].id}/state?worksheet_id={wid}").get_json()
    assert state["question"]["python_tutor_code"] == "x = 1\ny = x + 1"
