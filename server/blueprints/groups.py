import json
import random

from flask import Blueprint, jsonify, request

from server.auth import get_current_user, login_required, role_required
from server.config import Config
from server.extensions import db
from server.models.attempt import Attempt
from server.models.group import Group, GroupAssignmentProgress, GroupMembership, GroupQuestionState
from server.models.rating import Rating
from server.models.test_run import TestRun
from server.models.worksheet import Worksheet
from server.services import advance as advance_service
from server.services import compare as compare_service
from server.services import cooldown as cooldown_service
from server.services import grader_cooldown as grader_cooldown_service
from server.services import grading as grading_service
from server.services import serializers
from server.services import typist as typist_service
from server.services.predict_examples import extract_predict_examples_for_question
from server.utils import utcnow

groups_bp = Blueprint("groups", __name__)


def _load_group(group_id):
    return Group.query.get(group_id)


def _membership(group_id, user_id):
    if user_id is None:
        return None
    return GroupMembership.query.filter_by(group_id=group_id, user_id=user_id).first()


def _worksheet_id_from_args():
    raw = request.args.get("worksheet_id")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _worksheet_id_from_body(data):
    try:
        return int(data.get("worksheet_id"))
    except (TypeError, ValueError):
        return None


def _get_or_create_progress(group, worksheet_id):
    progress = GroupAssignmentProgress.query.filter_by(group_id=group.id, worksheet_id=worksheet_id).first()
    if progress is None:
        progress = GroupAssignmentProgress(group_id=group.id, worksheet_id=worksheet_id)
        db.session.add(progress)
        db.session.commit()
    return progress


def _get_or_create_state(group, question):
    state = GroupQuestionState.query.filter_by(group_id=group.id, question_id=question.id).first()
    if state is None:
        examples = extract_predict_examples_for_question(question)
        predict_example = random.choice(examples) if examples else None
        state = GroupQuestionState(
            group_id=group.id,
            question_id=question.id,
            code=question.starter_code or "",
            predict_example_json=json.dumps(predict_example) if predict_example else None,
        )
        db.session.add(state)
        db.session.commit()
    return state


@groups_bp.get("/<int:group_id>/state")
@login_required
def get_state(group_id):
    group = _load_group(group_id)
    if group is None:
        return jsonify(error="group not found"), 404

    worksheet_id = _worksheet_id_from_args()
    if worksheet_id is None:
        return jsonify(error="worksheet_id query param is required"), 400

    user = get_current_user()
    membership = _membership(group_id, user.id)
    if membership is None and user.role != "ta":
        return jsonify(error="not a member of this group"), 403

    worksheet = Worksheet.query.get(worksheet_id)
    if worksheet is None:
        return jsonify(error="assignment not found"), 404
    if user.role != "ta" and not worksheet.is_published:
        return jsonify(error="this assignment hasn't been released yet"), 403

    if membership is not None:
        membership.last_seen_at = utcnow()
        db.session.commit()

    progress = _get_or_create_progress(group, worksheet_id)
    question = serializers.current_question(worksheet_id, progress.current_question_index)
    state = _get_or_create_state(group, question) if question is not None else None

    return jsonify(**serializers.build_group_state(group, progress, user, state))


@groups_bp.put("/<int:group_id>/code")
@login_required
def update_code(group_id):
    group = _load_group(group_id)
    if group is None:
        return jsonify(error="group not found"), 404

    data = request.get_json(silent=True) or {}
    worksheet_id = _worksheet_id_from_body(data)
    if worksheet_id is None:
        return jsonify(error="worksheet_id is required"), 400

    user = get_current_user()
    progress = _get_or_create_progress(group, worksheet_id)
    if progress.typist_user_id != user.id:
        return jsonify(error="only the current typist can edit the code"), 403

    question = serializers.current_question(worksheet_id, progress.current_question_index)
    if question is None:
        return jsonify(error="worksheet already completed"), 409

    state = _get_or_create_state(group, question)
    state.code = data.get("code", "")
    state.updated_at = utcnow()
    db.session.commit()
    return jsonify(ok=True)


@groups_bp.post("/<int:group_id>/typist/claim")
@login_required
def claim_typist(group_id):
    group = _load_group(group_id)
    if group is None:
        return jsonify(error="group not found"), 404

    data = request.get_json(silent=True) or {}
    worksheet_id = _worksheet_id_from_body(data)
    if worksheet_id is None:
        return jsonify(error="worksheet_id is required"), 400

    user = get_current_user()
    if _membership(group_id, user.id) is None:
        return jsonify(error="not a member of this group"), 403

    progress = _get_or_create_progress(group, worksheet_id)
    if typist_service.claim_typist(progress, group_id, user.id):
        return jsonify(ok=True)

    db.session.refresh(progress)
    current = _membership(group_id, progress.typist_user_id)
    return (
        jsonify(
            error="someone else is already typist",
            current_typist=current.user.display_name if current else None,
        ),
        409,
    )


@groups_bp.post("/<int:group_id>/typist/pass")
@login_required
def pass_typist(group_id):
    group = _load_group(group_id)
    if group is None:
        return jsonify(error="group not found"), 404

    data = request.get_json(silent=True) or {}
    worksheet_id = _worksheet_id_from_body(data)
    if worksheet_id is None:
        return jsonify(error="worksheet_id is required"), 400
    to_user_id = data.get("to_user_id")

    user = get_current_user()
    if _membership(group_id, to_user_id) is None:
        return jsonify(error="target user is not a member of this group"), 400

    progress = _get_or_create_progress(group, worksheet_id)
    if typist_service.pass_typist(progress, user.id, to_user_id):
        return jsonify(ok=True)

    return jsonify(error="you are not the current typist"), 409


@groups_bp.post("/<int:group_id>/attempts")
@login_required
def submit_attempt(group_id):
    group = _load_group(group_id)
    if group is None:
        return jsonify(error="group not found"), 404

    data = request.get_json(silent=True) or {}
    worksheet_id = _worksheet_id_from_body(data)
    if worksheet_id is None:
        return jsonify(error="worksheet_id is required"), 400

    user = get_current_user()
    progress = _get_or_create_progress(group, worksheet_id)
    if progress.typist_user_id != user.id:
        return jsonify(error="only the current typist can run an attempt"), 403

    question = serializers.current_question(worksheet_id, progress.current_question_index)
    if question is None:
        return jsonify(error="worksheet already completed"), 409

    prediction = (data.get("prediction") or "").strip()
    if not prediction:
        return jsonify(error="a prediction is required before running"), 400

    if not cooldown_service.try_acquire(progress):
        return (
            jsonify(error="cooldown active", remaining_seconds=cooldown_service.remaining_seconds(progress)),
            429,
        )

    state = _get_or_create_state(group, question)
    is_match = compare_service.normalize_and_compare(prediction, question.expected_output)

    db.session.add(
        Attempt(
            group_id=group.id,
            question_id=question.id,
            user_id=user.id,
            prediction_text=prediction,
            is_match=is_match,
            code_snapshot=state.code,
        )
    )
    db.session.commit()

    return jsonify(is_match=is_match, expected_output=question.expected_output)


@groups_bp.post("/<int:group_id>/ratings")
@login_required
def submit_rating(group_id):
    group = _load_group(group_id)
    if group is None:
        return jsonify(error="group not found"), 404

    data = request.get_json(silent=True) or {}
    worksheet_id = _worksheet_id_from_body(data)
    if worksheet_id is None:
        return jsonify(error="worksheet_id is required"), 400

    user = get_current_user()
    if _membership(group_id, user.id) is None:
        return jsonify(error="not a member of this group"), 403

    progress = _get_or_create_progress(group, worksheet_id)
    question = serializers.current_question(worksheet_id, progress.current_question_index)
    if question is None:
        return jsonify(error="worksheet already completed"), 409

    value = data.get("value")
    if value not in (1, 2, 3, 4, 5):
        return jsonify(error="value must be an integer 1-5"), 400

    rating = Rating.query.filter_by(group_id=group.id, question_id=question.id, user_id=user.id).first()
    if rating is None:
        db.session.add(Rating(group_id=group.id, question_id=question.id, user_id=user.id, value=value))
    else:
        rating.value = value
        rating.updated_at = utcnow()
    db.session.commit()

    return jsonify(ok=True)


@groups_bp.post("/<int:group_id>/advance")
@login_required
def advance(group_id):
    group = _load_group(group_id)
    if group is None:
        return jsonify(error="group not found"), 404

    data = request.get_json(silent=True) or {}
    worksheet_id = _worksheet_id_from_body(data)
    if worksheet_id is None:
        return jsonify(error="worksheet_id is required"), 400

    user = get_current_user()
    if _membership(group_id, user.id) is None:
        return jsonify(error="not a member of this group"), 403

    progress = _get_or_create_progress(group, worksheet_id)
    question = serializers.current_question(worksheet_id, progress.current_question_index)
    if question is None:
        return jsonify(error="worksheet already completed"), 409

    success, error = advance_service.try_advance(progress, group_id, question.id)
    if not success:
        return jsonify(error=error), 409

    return jsonify(ok=True)


@groups_bp.post("/<int:group_id>/go-back")
@login_required
def go_back(group_id):
    group = _load_group(group_id)
    if group is None:
        return jsonify(error="group not found"), 404

    data = request.get_json(silent=True) or {}
    worksheet_id = _worksheet_id_from_body(data)
    if worksheet_id is None:
        return jsonify(error="worksheet_id is required"), 400

    user = get_current_user()
    if _membership(group_id, user.id) is None:
        return jsonify(error="not a member of this group"), 403

    progress = _get_or_create_progress(group, worksheet_id)
    success, error = advance_service.try_go_back(progress)
    if not success:
        return jsonify(error=error), 409

    return jsonify(ok=True)


@groups_bp.get("/<int:group_id>/solution")
@role_required("ta")
def get_solution(group_id):
    group = _load_group(group_id)
    if group is None:
        return jsonify(error="group not found"), 404

    worksheet_id = _worksheet_id_from_args()
    if worksheet_id is None:
        return jsonify(error="worksheet_id query param is required"), 400

    progress = _get_or_create_progress(group, worksheet_id)
    question = serializers.current_question(worksheet_id, progress.current_question_index)
    if question is None:
        return jsonify(error="worksheet already completed"), 409

    return jsonify(solution_markdown=question.solution_markdown)


@groups_bp.post("/<int:group_id>/run-tests")
@login_required
def run_tests(group_id):
    group = _load_group(group_id)
    if group is None:
        return jsonify(error="group not found"), 404

    data = request.get_json(silent=True) or {}
    worksheet_id = _worksheet_id_from_body(data)
    if worksheet_id is None:
        return jsonify(error="worksheet_id is required"), 400

    user = get_current_user()
    if _membership(group_id, user.id) is None:
        return jsonify(error="not a member of this group"), 403

    source = data.get("source")
    if source not in ("shared", "scratch"):
        return jsonify(error="source must be 'shared' or 'scratch'"), 400

    progress = _get_or_create_progress(group, worksheet_id)
    if source == "shared" and progress.typist_user_id != user.id:
        return jsonify(error="only the current typist can run tests against the shared code"), 403

    question = serializers.current_question(worksheet_id, progress.current_question_index)
    if question is None:
        return jsonify(error="worksheet already completed"), 409

    code = data.get("code")
    if not code or not code.strip():
        return jsonify(error="code is required"), 400

    prediction = (data.get("prediction") or "").strip()
    if not prediction:
        return jsonify(error="a prediction is required before running tests"), 400

    if not grader_cooldown_service.try_acquire(user):
        return (
            jsonify(
                error="cooldown active",
                remaining_seconds=grader_cooldown_service.remaining_seconds(user),
                cooldown_seconds=Config.GRADER_COOLDOWN_SECONDS,
            ),
            429,
        )

    results = grading_service.run_grader(question, code)
    results["cooldown_seconds"] = Config.GRADER_COOLDOWN_SECONDS

    state = _get_or_create_state(group, question)
    prediction_feedback = None
    if state.predict_example_json:
        example = json.loads(state.predict_example_json)
        prediction_feedback = {
            "call": example["call"],
            "expected": example["expected"],
            "got": prediction,
            "is_match": compare_service.normalize_and_compare(prediction, example["expected"]),
        }
    results["prediction_feedback"] = prediction_feedback

    db.session.add(
        TestRun(
            group_id=group.id,
            question_id=question.id,
            user_id=user.id,
            source=source,
            prediction_text=prediction,
            code_snapshot=code,
            passed_count=results.get("passed_count", 0),
            total_count=results.get("total_count", 0),
            total_points=results.get("total_points", 0),
            max_points=results.get("max_points", 0),
            results_json=json.dumps(results),
        )
    )
    db.session.commit()

    return jsonify(**results)


@groups_bp.get("/<int:group_id>/detail")
@role_required("ta")
def get_detail(group_id):
    group = _load_group(group_id)
    if group is None:
        return jsonify(error="group not found"), 404

    worksheet_id = _worksheet_id_from_args()
    if worksheet_id is None:
        return jsonify(error="worksheet_id query param is required"), 400

    progress = _get_or_create_progress(group, worksheet_id)
    question = serializers.current_question(worksheet_id, progress.current_question_index)
    state = GroupQuestionState.query.filter_by(group_id=group.id, question_id=question.id).first() if question else None

    return jsonify(**serializers.build_group_detail(group, progress, state))


@groups_bp.post("/<int:group_id>/typist/release")
@role_required("ta")
def release_typist_route(group_id):
    group = _load_group(group_id)
    if group is None:
        return jsonify(error="group not found"), 404

    data = request.get_json(silent=True) or {}
    worksheet_id = _worksheet_id_from_body(data)
    if worksheet_id is None:
        return jsonify(error="worksheet_id is required"), 400

    progress = _get_or_create_progress(group, worksheet_id)
    typist_service.release_typist(progress)
    return jsonify(ok=True)
