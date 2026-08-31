import json
from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from server.config import Config
from server.extensions import db
from server.models.attempt import Attempt
from server.models.group import Group, GroupAssignmentProgress, GroupMembership, GroupQuestionState, ScratchCode
from server.models.question_response import QuestionResponse
from server.models.rating import Rating
from server.models.test_run import TestRun
from server.models.worksheet import Question, Worksheet
from server.services import advance as advance_service
from server.services import cooldown as cooldown_service
from server.services import grader_cooldown as grader_cooldown_service
from server.services import response_grading
from server.services.predict_examples import extract_predict_examples_for_question
from server.utils import utcnow

TA_ATTEMPT_HISTORY_LIMIT = 20


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


def build_group_state(group, progress, user, state):
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
    my_scratch = ScratchCode.query.filter_by(group_id=group.id, question_id=question.id, user_id=user.id).first()
    predict_call = None
    if state.predict_example_json:
        predict_call = json.loads(state.predict_example_json)["call"]

    members = GroupMembership.query.options(joinedload(GroupMembership.user)).filter_by(group_id=group.id).all()
    stale_cutoff = utcnow() - timedelta(seconds=Config.TYPIST_STALE_SECONDS)

    # One query for every member's rating on this question instead of one
    # per member — this runs on every ~2.5s /state poll for every active
    # group, so an N+1 here scales with total concurrent groups, not just
    # this group's size.
    ratings_by_user = {
        r.user_id: r for r in Rating.query.filter_by(group_id=group.id, question_id=question.id).all()
    }

    member_payload = []
    my_rating = None
    for m in members:
        rating = ratings_by_user.get(m.user_id)
        if m.user_id == user.id:
            my_rating = rating.value if rating else None
        member_payload.append(
            {
                "user_id": m.user_id,
                "display_name": m.user.display_name,
                "is_typist": progress.typist_user_id == m.user_id,
                "is_typist_stale": progress.typist_user_id == m.user_id and m.last_seen_at < stale_cutoff,
                "has_rated_current": rating is not None,
                "is_me": m.user_id == user.id,
                # Recently polled /state — the "live count" only counts
                # these, and the pen is only ever (re)assigned among them.
                "is_active": m.last_seen_at >= stale_cutoff,
            }
        )

    last_attempt_row = (
        Attempt.query.filter_by(group_id=group.id, question_id=question.id)
        .order_by(Attempt.created_at.desc())
        .first()
    )
    last_attempt = None
    if last_attempt_row is not None:
        last_attempt = {
            "prediction": last_attempt_row.prediction_text,
            "is_match": last_attempt_row.is_match,
            "expected_output": question.expected_output,
            "by": last_attempt_row.user.display_name,
        }

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
            last_shared_run["by"] = last_shared_run_row.user.display_name

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
            # 'coding' behaves exactly as before; other values drive a
            # non-code answer widget on the client. `content` here is the
            # answer-stripped public view (see response_grading).
            "problem_type": question.problem_type or "coding",
            "content": response_grading.public_content(question),
            # expected_output is deliberately withheld here (only surfaces
            # in last_attempt once someone has actually run it) — the same
            # hygiene now applies to solution_markdown (never included in
            # /state, only fetched on demand via GET /groups/:id/solution)
            # and to the predict_example's expected value, which is never
            # sent — only the call to predict is (predict_call).
            "has_predict_flow": bool(question.expected_output),
            "predict_call": predict_call,
        },
        "worksheet_title": worksheet_title,
        "total_questions": total_questions_for_worksheet(progress.worksheet_id),
        "code": code,
        "my_scratch_code": my_scratch.code if my_scratch else "",
        "cooldown": {
            "active": cooldown_service.is_active(progress),
            "remaining_seconds": cooldown_service.remaining_seconds(progress),
        },
        "grader_cooldown": {
            "remaining_seconds": grader_cooldown_service.remaining_seconds(user),
            "cooldown_seconds": grader_cooldown_service.cooldown_seconds_for(user),
        },
        "members": member_payload,
        "my_rating_value": my_rating,
        "last_attempt": last_attempt,
        "last_shared_run": last_shared_run,
        # The group's shared answer to a non-code question (null for coding).
        "group_response": group_answer,
        "group_response_correct": group_answer_correct,
        "all_rated": advance_service.all_members_rated(group.id, question.id),
        "has_passing_run": advance_service.has_passing_shared_run(group.id, question.id),
        "ready_to_advance": advance_service.ready_to_advance(group.id, question.id),
    }


def build_group_detail(group, progress, state):
    """TA-only detail view: unlike the student /state payload, this reveals
    expected_output up front and includes recent attempt history, since a TA
    is trusted with the answer regardless of whether the group has run yet.
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

    members = GroupMembership.query.options(joinedload(GroupMembership.user)).filter_by(group_id=group.id).all()
    ratings_by_user = {
        r.user_id: r for r in Rating.query.filter_by(group_id=group.id, question_id=question.id).all()
    }
    member_payload = []
    for m in members:
        rating = ratings_by_user.get(m.user_id)
        member_payload.append(
            {
                "user_id": m.user_id,
                "display_name": m.user.display_name,
                "is_typist": progress.typist_user_id == m.user_id,
                "rating": rating.value if rating else None,
            }
        )

    attempts = (
        Attempt.query.filter_by(group_id=group.id, question_id=question.id)
        .order_by(Attempt.created_at.desc())
        .limit(TA_ATTEMPT_HISTORY_LIMIT)
        .all()
    )
    attempt_payload = [
        {
            "prediction": a.prediction_text,
            "is_match": a.is_match,
            "by": a.user.display_name,
            "created_at": a.created_at.isoformat(),
        }
        for a in attempts
    ]

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
        },
        "group_response": ta_group_answer,
        "group_response_correct": ta_group_answer_correct,
        "total_questions": total_questions_for_worksheet(progress.worksheet_id),
        "code": code,
        "members": member_payload,
        "attempts": attempt_payload,
        "cooldown": {
            "active": cooldown_service.is_active(progress),
            "remaining_seconds": cooldown_service.remaining_seconds(progress),
        },
    }


def build_dashboard(worksheet_id, groups):
    """`groups` is the list of Group rows in the class. Groups with no
    GroupAssignmentProgress row yet for this worksheet (haven't opened this
    assignment) are reported at question 0, not stuck.
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
    for group in groups:
        progress = GroupAssignmentProgress.query.filter_by(group_id=group.id, worksheet_id=worksheet_id).first()
        current_index = progress.current_question_index if progress else 0
        typist_user_id = progress.typist_user_id if progress else None
        question_started_at = progress.question_started_at if progress else None

        members = GroupMembership.query.options(joinedload(GroupMembership.user)).filter_by(group_id=group.id).all()
        question = current_question(worksheet_id, current_index)

        ratings_by_user = {}
        if question is not None:
            ratings_by_user = {
                r.user_id: r.value
                for r in Rating.query.filter_by(group_id=group.id, question_id=question.id).all()
            }

        member_payload = [
            {"user_id": m.user_id, "display_name": m.user.display_name, "rating": ratings_by_user.get(m.user_id)}
            for m in members
        ]

        typist_name = next((m.user.display_name for m in members if m.user_id == typist_user_id), None)
        completed = question is None
        if completed:
            status = "done"
        elif question_started_at is not None and question_started_at < stuck_cutoff:
            status = "stuck"
        else:
            status = "on_pace"

        avg_rating = avg_rating_by_group.get(group.id)

        payload.append(
            {
                "group_id": group.id,
                "name": group.name,
                "current_question_index": current_index,
                "total_questions": total,
                "typist_name": typist_name,
                "members": member_payload,
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
        Worksheet.query.filter_by(class_id=group.section.class_id, is_published=True)
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


def build_section_progress(section):
    """One row per (non-individual) group in this section: its roster and a
    general progress meter across every published assignment in its class —
    how many it's completed, and its average confidence rating across
    everything it's rated so far. Backs the "Discussions" tab's per-section
    view (server/blueprints/sections.py:section_progress), which is
    deliberately just roster + progress, not assignment content — that
    lives on the class's "Assignments" tab instead.
    """
    groups = Group.query.filter_by(section_id=section.id, is_individual=False).order_by(Group.number).all()
    payload = []
    for group in groups:
        members = GroupMembership.query.filter_by(group_id=group.id).all()
        history = build_group_history(group)
        total = len(history)
        completed = sum(1 for h in history if h["status"] == "completed")
        avg_rating = db.session.query(func.avg(Rating.value)).filter_by(group_id=group.id).scalar()
        payload.append(
            {
                "group_id": group.id,
                "number": group.number,
                "name": group.name,
                "member_names": [m.user.display_name for m in members],
                "assignments_completed": completed,
                "total_assignments": total,
                "average_rating": round(avg_rating, 1) if avg_rating is not None else None,
            }
        )
    return payload


def student_worksheet_progress(user, worksheet):
    """(my_rating, my_group_id) for `user`'s own engagement with
    `worksheet`, via whichever of their groups has progress on it —
    (None, None) if they haven't started it via any group yet. Backs the
    shared Assignments page's per-row rating display (server/blueprints/
    sections.py:_serialize_worksheet) — unlike the old "My Assignments"
    view this replaced, it's not restricted to *completed* assignments,
    since the page now lists every assignment in the class regardless of
    where a student's group currently stands on it.

    If a student has more than one group with progress on this worksheet
    (e.g. they switched sections), the most recently active one wins —
    rare in practice, and there's no single "correct" answer for that case.
    """
    membership_group_ids = [m.group_id for m in GroupMembership.query.filter_by(user_id=user.id).all()]
    if not membership_group_ids:
        return None, None

    progress = (
        GroupAssignmentProgress.query.filter(
            GroupAssignmentProgress.worksheet_id == worksheet.id,
            GroupAssignmentProgress.group_id.in_(membership_group_ids),
        )
        .order_by(GroupAssignmentProgress.question_started_at.desc())
        .first()
    )
    if progress is None:
        return None, None

    question_ids = [
        q.id for q in Question.query.filter_by(worksheet_id=worksheet.id).with_entities(Question.id).all()
    ]
    my_avg_rating = (
        db.session.query(func.avg(Rating.value))
        .filter(Rating.user_id == user.id, Rating.question_id.in_(question_ids), Rating.group_id == progress.group_id)
        .scalar()
        if question_ids
        else None
    )
    return (round(my_avg_rating, 1) if my_avg_rating is not None else None), progress.group_id


def _predict_call_for(group, question):
    """The same {call, ...} a live/current view of this question would show
    (server/blueprints/groups.py:_get_or_create_state) — reused here rather
    than randomly re-picked, so browsing back to a question shows the exact
    call the group was actually quizzed on while it was current. Falls back
    to computing one fresh (deterministically, the first candidate — not
    random.choice, so it doesn't change on every page load) for a question
    that was unlocked but never actually made current, which shouldn't
    normally happen but isn't worth a hard failure over.
    """
    state = GroupQuestionState.query.filter_by(group_id=group.id, question_id=question.id).first()
    if state is not None and state.predict_example_json:
        return json.loads(state.predict_example_json)["call"]
    examples = extract_predict_examples_for_question(question)
    return examples[0]["call"] if examples else None


def build_group_work(group, worksheet_id, user):
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

    `scratch_code` is `user`'s own personal practice code for that
    question (ScratchCode), not the group's shared one — the whole reason
    it's persisted server-side rather than only in browser localStorage is
    so it's still visible here, not just live while working.
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
        scratch = ScratchCode.query.filter_by(group_id=group.id, question_id=question.id, user_id=user.id).first()
        rating = Rating.query.filter_by(group_id=group.id, question_id=question.id, user_id=user.id).first()
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
                "group_response": group_answer,
                "group_response_correct": group_answer_correct,
                "code": latest_run.code_snapshot if latest_run else None,
                "starter_code": question.starter_code or "",
                "passed": advance_service.has_ever_passed_tests(group.id, question.id),
                "scratch_code": scratch.code if scratch and scratch.code else None,
                "predict_call": _predict_call_for(group, question),
                "my_rating": rating.value if rating else None,
            }
        )
    return {"worksheet_title": worksheet.title, "questions": payload}
