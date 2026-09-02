import json
from datetime import timedelta

from sqlalchemy import func

from server.config import Config
from server.extensions import db
from server.models.group import Group, GroupAssignmentProgress, GroupMembership, GroupQuestionState, ScratchCode
from server.models.question_response import QuestionResponse
from server.models.rating import Rating
from server.models.test_run import TestRun
from server.models.worksheet import Question, Worksheet
from server.services import advance as advance_service
from server.services import cooldown as cooldown_service
from server.models.group_prediction import GroupPrediction
from server.services import presence
from server.services import response_grading
from server.utils import utcnow


def _member_names(group_id):
    """{participant_key: participant_name} for a group — the one place a
    name lives now (GroupMembership); every other participant-scoped row
    carries only the key."""
    return {
        m.participant_key: m.participant_name
        for m in GroupMembership.query.filter_by(group_id=group_id).all()
    }


def current_question(worksheet_id, current_question_index):
    return Question.query.filter_by(worksheet_id=worksheet_id, order_index=current_question_index).first()


def total_questions_for_worksheet(worksheet_id):
    return Question.query.filter_by(worksheet_id=worksheet_id).count()


def _group_response(group_id, question_id):
    """(parsed_answer_or_None, is_correct_or_None) for a group's shared
    answer to a non-code question."""
    row = QuestionResponse.query.filter_by(group_id=group_id, question_id=question_id).first()
    if row is None:
        return None, None
    try:
        answer = json.loads(row.response_json) if row.response_json else None
    except (ValueError, TypeError):
        answer = None
    return answer, row.is_correct


def question_prediction_config(question):
    try:
        return json.loads(question.prediction_json) if question.prediction_json else None
    except (ValueError, TypeError):
        return None


def group_prediction_item(question, group_id):
    """The output-prediction item this group drew — {index, code, expected}
    — from GroupQuestionState.predict_example_json (see
    server/blueprints/groups.py:_get_or_create_state), or None."""
    pred = question_prediction_config(question)
    if not pred or pred.get("mode") != "output":
        return None
    state = GroupQuestionState.query.filter_by(group_id=group_id, question_id=question.id).first()
    idx = None
    if state and state.predict_example_json:
        try:
            idx = json.loads(state.predict_example_json).get("prediction_item")
        except (ValueError, AttributeError):
            idx = None
    items = pred.get("items") or []
    if not isinstance(idx, int) or not 0 <= idx < len(items):
        return None
    return {"index": idx, **items[idx]}


def build_prediction(question, group_id):
    """The `prediction` object in the student /state payload, or None when
    the question has no prediction prompt. Never leaks expected outputs."""
    pred = question_prediction_config(question)
    if not pred:
        return None
    row = GroupPrediction.query.filter_by(group_id=group_id, question_id=question.id).first()
    out = {
        "mode": pred.get("mode", "output"),
        "group_answer": row.prediction_text if row else None,
        "group_correct": row.is_correct if row else None,
    }
    if pred.get("mode") == "written":
        out["prompt"] = pred.get("prompt", "")
    else:
        item = group_prediction_item(question, group_id)
        out["setup"] = pred.get("setup", "")
        out["item"] = {"index": item["index"], "code": item["code"]} if item else None
    return out


def build_group_state(group, progress, participant_key, state):
    # A group can have several worksheets in flight independently (each
    # gets its own GroupAssignmentProgress/typist) — the title is here so
    # the page can say *which one* you're looking at. Without it, two
    # members on different worksheets in the same group would see
    # identically-labeled pages ("Group 3") with no way to notice they're
    # not actually looking at the same assignment.
    worksheet_title = Worksheet.query.get(progress.worksheet_id).title

    question = current_question(progress.worksheet_id, progress.current_question_index)
    if question is None:
        return {
            "group": {
                "id": group.id,
                "name": group.name,
                "current_question_index": progress.current_question_index,
                "completed": True,
                "is_individual": group.is_individual,
            },
            "worksheet_title": worksheet_title,
            "total_questions": total_questions_for_worksheet(progress.worksheet_id),
        }

    code = state.code
    my_scratch = ScratchCode.query.filter_by(
        group_id=group.id, question_id=question.id, participant_key=participant_key
    ).first()

    members = GroupMembership.query.filter_by(group_id=group.id).all()
    stale_cutoff = utcnow() - timedelta(seconds=Config.TYPIST_STALE_SECONDS)

    # One query for every member's rating on this question instead of one
    # per member — this runs on every ~2.5s /state poll for every active
    # group, so an N+1 here scales with total concurrent groups, not just
    # this group's size.
    ratings_by_key = {
        r.participant_key: r for r in Rating.query.filter_by(group_id=group.id, question_id=question.id).all()
    }

    member_payload = []
    my_rating = None
    for m in members:
        rating = ratings_by_key.get(m.participant_key)
        if m.participant_key == participant_key:
            my_rating = rating.value if rating else None
        member_payload.append(
            {
                # An opaque per-session participant key, not a users.id.
                "user_id": m.participant_key,
                "display_name": m.participant_name,
                "is_typist": progress.typist_key == m.participant_key,
                "is_typist_stale": progress.typist_key == m.participant_key and m.last_seen_at < stale_cutoff,
                "has_rated_current": rating is not None,
                "is_me": m.participant_key == participant_key,
                # Recently polled /state — the "live count" only counts
                # these, and the pen is only ever (re)assigned among them.
                "is_active": m.last_seen_at >= stale_cutoff,
            }
        )

    # Only the browser that clicked "Run tests" ever sees the outcome
    # locally — surfacing the group's last shared run here means every
    # member sees the same pass/fail confirmation once the typist's code
    # passes, not just the typist themselves.
    last_shared_run_row = (
        TestRun.query.filter_by(group_id=group.id, question_id=question.id, source="shared", status="done")
        .order_by(TestRun.created_at.desc())
        .first()
    )
    last_shared_run = None
    if last_shared_run_row is not None:
        try:
            last_shared_run = json.loads(last_shared_run_row.results_json)
        except ValueError:
            last_shared_run = None
        if last_shared_run is not None:
            last_shared_run["by"] = _member_names(group.id).get(last_shared_run_row.participant_key, "a groupmate")

    group_answer, group_answer_correct = _group_response(group.id, question.id)

    return {
        "group": {
            "id": group.id,
            "name": group.name,
            "current_question_index": progress.current_question_index,
            "completed": False,
            "is_individual": group.is_individual,
        },
        "question": {
            "id": question.id,
            "order_index": question.order_index,
            "title": question.title,
            "prompt": question.prompt,
            "starter_code": question.starter_code,
            "language": question.language,
            "grading_mode": question.grading_mode,
            # Grading runs in the browser now (Pyodide), so the harness needs
            # the setup + test code client-side. For a discussion tool having
            # students able to read the tests is an acceptable trade
            # (doctest questions already show them).
            "setup_code": question.setup_code or "",
            "test_code": question.test_code or "",
            # 'coding' behaves exactly as before; other values drive a
            # non-code answer widget on the client. `content` here is the
            # answer-stripped public view (see response_grading).
            "problem_type": question.problem_type or "coding",
            "content": response_grading.public_content(question),
            # The optional prediction prompt (any problem_type), answer
            # stripped. null when the question has none. solution_markdown is
            # likewise withheld — fetched on demand via GET /groups/:id/solution.
            "prediction": build_prediction(question, group.id),
            "python_tutor_code": question.python_tutor_code or "",
        },
        "worksheet_title": worksheet_title,
        "total_questions": total_questions_for_worksheet(progress.worksheet_id),
        "code": code,
        "my_scratch_code": my_scratch.code if my_scratch else "",
        "cooldown": {
            "active": cooldown_service.is_active(progress),
            "remaining_seconds": cooldown_service.remaining_seconds(progress),
        },
        "members": member_payload,
        "my_rating_value": my_rating,
        "last_shared_run": last_shared_run,
        # The group's shared answer to a non-code question (null for coding).
        "group_response": group_answer,
        "group_response_correct": group_answer_correct,
        "all_rated": advance_service.all_members_rated(group.id, question.id),
        "has_passing_run": advance_service.has_passing_shared_run(group.id, question.id),
        "prediction_ready": advance_service.prediction_gate_met(group.id, question),
        "ready_to_advance": advance_service.ready_to_advance(group.id, question.id),
    }


def build_group_detail(group, progress, state):
    """TA-only detail view: unlike the student /state payload, this reveals
    expected_output up front, since a TA is trusted with the answer
    regardless of whether the group has run yet.
    """
    question = current_question(progress.worksheet_id, progress.current_question_index)
    if question is None:
        return {
            "group": {
                "id": group.id,
                "name": group.name,
                "current_question_index": progress.current_question_index,
                "completed": True,
            },
            "total_questions": total_questions_for_worksheet(progress.worksheet_id),
        }

    code = state.code if state is not None else (question.starter_code or "")
    ta_group_answer, ta_group_answer_correct = _group_response(group.id, question.id)

    members = GroupMembership.query.filter_by(group_id=group.id).all()
    ratings_by_key = {
        r.participant_key: r for r in Rating.query.filter_by(group_id=group.id, question_id=question.id).all()
    }
    member_payload = []
    for m in members:
        rating = ratings_by_key.get(m.participant_key)
        member_payload.append(
            {
                "user_id": m.participant_key,
                "display_name": m.participant_name,
                "is_typist": progress.typist_key == m.participant_key,
                "rating": rating.value if rating else None,
            }
        )

    return {
        "group": {
            "id": group.id,
            "name": group.name,
            "current_question_index": progress.current_question_index,
            "completed": False,
        },
        "question": {
            "id": question.id,
            "order_index": question.order_index,
            "title": question.title,
            "prompt": question.prompt,
            "expected_output": question.expected_output,
            "language": question.language,
            "grading_mode": question.grading_mode,
            # TA view — full content incl. answers, plus the group's answer.
            "problem_type": question.problem_type or "coding",
            "content": (
                response_grading.parse_content(question)
                if (question.problem_type or "coding") != "coding"
                else None
            ),
            "prediction": question_prediction_config(question),
            "python_tutor_code": question.python_tutor_code or "",
        },
        "group_response": ta_group_answer,
        "group_response_correct": ta_group_answer_correct,
        "total_questions": total_questions_for_worksheet(progress.worksheet_id),
        "code": code,
        "members": member_payload,
        # Per-participant prediction-quiz history (Attempt) was removed with
        # the anonymous-session redesign; kept as an empty list for the
        # TA detail pane's shape.
        "attempts": [],
        "cooldown": {
            "active": cooldown_service.is_active(progress),
            "remaining_seconds": cooldown_service.remaining_seconds(progress),
        },
    }


def build_dashboard(worksheet_id, entries):
    """`entries` is [(number, Group|None)] — one per group number the TA is
    watching. A `None` group is a watched number nobody has entered yet
    (an "empty" tile). A group with no GroupAssignmentProgress for this
    worksheet is reported at question 0, not stuck. `present` is the
    display names currently logged into the group (recent /state polls).
    """
    stuck_cutoff = utcnow() - timedelta(seconds=Config.STUCK_THRESHOLD_SECONDS)
    total = total_questions_for_worksheet(worksheet_id)

    question_ids = [
        q.id for q in Question.query.filter_by(worksheet_id=worksheet_id).with_entities(Question.id).all()
    ]
    avg_rating_by_group = {}
    if question_ids:
        rows = (
            db.session.query(Rating.group_id, func.avg(Rating.value))
            .filter(Rating.question_id.in_(question_ids))
            .group_by(Rating.group_id)
            .all()
        )
        avg_rating_by_group = {group_id: avg_value for group_id, avg_value in rows}

    payload = []
    for number, group in entries:
        if group is None:
            payload.append(
                {
                    "group_id": None,
                    "number": number,
                    "name": None,
                    "current_question_index": 0,
                    "total_questions": total,
                    "typist_name": None,
                    "members": [],
                    "present": [],
                    "status": "empty",
                    "average_rating": None,
                }
            )
            continue

        progress = GroupAssignmentProgress.query.filter_by(group_id=group.id, worksheet_id=worksheet_id).first()
        current_index = progress.current_question_index if progress else 0
        typist_key = progress.typist_key if progress else None
        question_started_at = progress.question_started_at if progress else None

        members = GroupMembership.query.filter_by(group_id=group.id).all()
        active_keys = {m.participant_key for m in presence.active_members(group.id)}
        question = current_question(worksheet_id, current_index)

        ratings_by_key = {}
        if question is not None:
            ratings_by_key = {
                r.participant_key: r.value
                for r in Rating.query.filter_by(group_id=group.id, question_id=question.id).all()
            }

        member_payload = [
            {
                "user_id": m.participant_key,
                "display_name": m.participant_name,
                "rating": ratings_by_key.get(m.participant_key),
            }
            for m in members
        ]
        present = [m.participant_name for m in members if m.participant_key in active_keys]

        typist_name = next((m.participant_name for m in members if m.participant_key == typist_key), None)
        completed = question is None
        if completed:
            status = "done"
        elif not present:
            status = "empty"
        elif question_started_at is not None and question_started_at < stuck_cutoff:
            status = "stuck"
        else:
            status = "on_pace"

        avg_rating = avg_rating_by_group.get(group.id)

        payload.append(
            {
                "group_id": group.id,
                "number": number,
                "name": group.name,
                "current_question_index": current_index,
                "total_questions": total,
                "typist_name": typist_name,
                "members": member_payload,
                "present": present,
                "status": status,
                "average_rating": round(avg_rating, 1) if avg_rating is not None else None,
            }
        )
    return payload


def build_group_history(group):
    """Every published discussion this group has touched in its class, most
    recent first — visible to both the group's own students and its TA (see
    server/blueprints/groups.py:get_group_history). Draft worksheets are
    excluded even for a TA/admin viewer: this is "what this group has done"
    from the group's perspective, not an authoring surface.
    """
    worksheets = (
        Worksheet.query.filter_by(class_id=group.class_id, is_published=True)
        .order_by(Worksheet.created_at.desc())
        .all()
    )

    history = []
    for worksheet in worksheets:
        total_questions = Question.query.filter_by(worksheet_id=worksheet.id).count()
        progress = GroupAssignmentProgress.query.filter_by(group_id=group.id, worksheet_id=worksheet.id).first()

        if progress is None:
            status = "not_started"
            questions_completed = 0
        elif total_questions > 0 and progress.current_question_index >= total_questions:
            status = "completed"
            questions_completed = total_questions
        else:
            status = "in_progress"
            questions_completed = progress.current_question_index

        questions_passed = 0
        if progress is not None:
            for question in Question.query.filter_by(worksheet_id=worksheet.id).all():
                if advance_service.has_ever_passed_tests(group.id, question.id):
                    questions_passed += 1

        history.append(
            {
                "worksheet_id": worksheet.id,
                "title": worksheet.title,
                "status": status,
                "questions_completed": questions_completed,
                "total_questions": total_questions,
                "questions_passed": questions_passed,
            }
        )
    return history


def build_group_work(group, worksheet_id, participant_key):
    """Replay of this group's already-*unlocked* questions on one
    assignment and their most recent submitted code (the latest shared
    "Run tests" snapshot) — backs both the History page's "View work"
    section (a completed assignment, so every question is unlocked) and
    the live worksheet page's "view a previous question" navigation (an
    in-progress assignment, where only questions up to the group's current
    position are unlocked — a locked, not-yet-reached question's prompt is
    never included here). Either way, a viewer can re-run tests against
    what's returned for practice (POST .../practice-run in
    server/blueprints/groups.py) without touching the group's real
    progress/completed status.

    `passed` reflects whether the group *ever* passed this question
    (advance_service.has_ever_passed_tests), not whether the code shown
    right now would — code shown is always the latest submission, so a
    group optimizing an already-passing solution can keep resubmitting
    without their own "passed" badge flickering off if an in-progress
    attempt happens to fail.

    `scratch_code` is the requesting participant's own personal practice
    code for that question (ScratchCode), not the group's shared one.
    """
    worksheet = Worksheet.query.get_or_404(worksheet_id)
    progress = GroupAssignmentProgress.query.filter_by(group_id=group.id, worksheet_id=worksheet_id).first()
    unlocked_index = progress.current_question_index if progress is not None else 0

    questions = (
        Question.query.filter_by(worksheet_id=worksheet.id)
        .filter(Question.order_index <= unlocked_index)
        .order_by(Question.order_index)
        .all()
    )
    payload = []
    for question in questions:
        latest_run = (
            TestRun.query.filter_by(group_id=group.id, question_id=question.id, source="shared")
            .order_by(TestRun.created_at.desc())
            .first()
        )
        scratch = ScratchCode.query.filter_by(
            group_id=group.id, question_id=question.id, participant_key=participant_key
        ).first()
        rating = Rating.query.filter_by(
            group_id=group.id, question_id=question.id, participant_key=participant_key
        ).first()
        group_answer, group_answer_correct = _group_response(group.id, question.id)
        payload.append(
            {
                "question_id": question.id,
                "order_index": question.order_index,
                "title": question.title,
                "prompt": question.prompt,
                "grading_mode": question.grading_mode,
                "problem_type": question.problem_type or "coding",
                "content": response_grading.public_content(question),
                "prediction": build_prediction(question, group.id),
                "python_tutor_code": question.python_tutor_code or "",
                "group_response": group_answer,
                "group_response_correct": group_answer_correct,
                "code": latest_run.code_snapshot if latest_run else None,
                "starter_code": question.starter_code or "",
                "setup_code": question.setup_code or "",
                "test_code": question.test_code or "",
                "passed": advance_service.has_ever_passed_tests(group.id, question.id),
                "scratch_code": scratch.code if scratch and scratch.code else None,
                "my_rating": rating.value if rating else None,
            }
        )
    return {"worksheet_title": worksheet.title, "questions": payload}
