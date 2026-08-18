import json
from datetime import timedelta

from sqlalchemy import func

from server.config import Config
from server.extensions import db
from server.models.attempt import Attempt
from server.models.group import GroupAssignmentProgress, GroupMembership
from server.models.rating import Rating
from server.models.test_run import TestRun
from server.models.worksheet import Question
from server.services import advance as advance_service
from server.services import cooldown as cooldown_service
from server.services import grader_cooldown as grader_cooldown_service
from server.utils import utcnow

TA_ATTEMPT_HISTORY_LIMIT = 20


def current_question(worksheet_id, current_question_index):
    return Question.query.filter_by(worksheet_id=worksheet_id, order_index=current_question_index).first()


def total_questions_for_worksheet(worksheet_id):
    return Question.query.filter_by(worksheet_id=worksheet_id).count()


def build_group_state(group, progress, user, state):
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

    code = state.code
    predict_call = None
    if state.predict_example_json:
        predict_call = json.loads(state.predict_example_json)["call"]

    members = GroupMembership.query.filter_by(group_id=group.id).all()
    stale_cutoff = utcnow() - timedelta(seconds=Config.TYPIST_STALE_SECONDS)

    member_payload = []
    my_rating = None
    for m in members:
        rating = Rating.query.filter_by(group_id=group.id, question_id=question.id, user_id=m.user_id).first()
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
        TestRun.query.filter_by(group_id=group.id, question_id=question.id, source="shared")
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
            "starter_code": question.starter_code,
            "language": question.language,
            "difficulty": question.difficulty,
            # expected_output is deliberately withheld here (only surfaces
            # in last_attempt once someone has actually run it) — the same
            # hygiene now applies to solution_markdown (never included in
            # /state, only fetched on demand via GET /groups/:id/solution)
            # and to the predict_example's expected value, which is never
            # sent — only the call to predict is (predict_call).
            "has_predict_flow": bool(question.expected_output),
            "predict_call": predict_call,
        },
        "total_questions": total_questions_for_worksheet(progress.worksheet_id),
        "code": code,
        "cooldown": {
            "active": cooldown_service.is_active(progress),
            "remaining_seconds": cooldown_service.remaining_seconds(progress),
        },
        "grader_cooldown": {
            "remaining_seconds": grader_cooldown_service.remaining_seconds(user),
            "cooldown_seconds": Config.GRADER_COOLDOWN_SECONDS,
        },
        "members": member_payload,
        "my_rating_value": my_rating,
        "last_attempt": last_attempt,
        "last_shared_run": last_shared_run,
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

    members = GroupMembership.query.filter_by(group_id=group.id).all()
    member_payload = []
    for m in members:
        rating = Rating.query.filter_by(group_id=group.id, question_id=question.id, user_id=m.user_id).first()
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
            "difficulty": question.difficulty,
        },
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

        members = GroupMembership.query.filter_by(group_id=group.id).all()
        question = current_question(worksheet_id, current_index)

        member_payload = []
        for m in members:
            rating_value = None
            if question is not None:
                rating = Rating.query.filter_by(
                    group_id=group.id, question_id=question.id, user_id=m.user_id
                ).first()
                rating_value = rating.value if rating else None
            member_payload.append({"user_id": m.user_id, "display_name": m.user.display_name, "rating": rating_value})

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
