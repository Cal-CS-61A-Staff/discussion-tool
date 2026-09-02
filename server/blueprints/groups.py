import json
import random

from flask import Blueprint, jsonify, request

from server.auth import (
    get_current_user,
    is_class_staff,
    login_required,
    require_class_access,
    role_required,
)
from server.extensions import db
from server.models.attempt import Attempt
from server.models.group import Group, GroupAssignmentProgress, GroupMembership, GroupQuestionState, ScratchCode
from server.models.group_prediction import GroupPrediction
from server.models.question_response import QuestionResponse
from server.models.rating import Rating
from server.models.test_run import TestRun
from server.models.worksheet import Question, Worksheet
from server.services import advance as advance_service
from server.services import compare as compare_service
from server.services import cooldown as cooldown_service
from server.services import counterexample_grading
from server.services import grader_cooldown as grader_cooldown_service
from server.services import grading_queue as grading_queue_service
from server.services import response_grading
from server.services import serializers
from server.services import typist as typist_service
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


def _worksheet_for_group_or_error(group, worksheet_id, user):
    """None if `worksheet_id` may be used with `group` — i.e. it actually
    belongs to the group's own class, and (for non-staff) has been
    released — else a Flask error response to return as-is.

    Every route below that accepts a client-supplied worksheet_id must call
    this before touching progress/state/grading for it:
    `_get_or_create_progress` (and friends) only ever see a bare id, with
    no way to enforce this themselves, so without this check any
    authenticated student could probe, view, or even run real code through
    the sandboxed grader against ANY worksheet in the whole app — other
    classes' and unpublished drafts included — just by supplying its id.
    """
    worksheet = Worksheet.query.get(worksheet_id)
    if worksheet is None or worksheet.class_id != group.class_id:
        return jsonify(error="assignment not found"), 404
    if not is_class_staff(user, group.klass) and not worksheet.is_published:
        return jsonify(error="this assignment hasn't been released yet"), 403
    return None


def _get_or_create_progress(group, worksheet_id):
    progress = GroupAssignmentProgress.query.filter_by(group_id=group.id, worksheet_id=worksheet_id).first()
    if progress is None:
        progress = GroupAssignmentProgress(group_id=group.id, worksheet_id=worksheet_id)
        db.session.add(progress)
        db.session.commit()
        # A group's first question also needs a typist — every later
        # question gets one via advance_service, this covers question one.
        typist_service.assign_random_typist(progress, group.id)
    return progress


def _prediction_of(question):
    try:
        return json.loads(question.prediction_json) if question.prediction_json else None
    except (ValueError, TypeError):
        return None


def _get_or_create_state(group, question):
    state = GroupQuestionState.query.filter_by(group_id=group.id, question_id=question.id).first()
    if state is None:
        predict_example = None
        pred = _prediction_of(question)
        if pred and pred.get("mode") == "output" and pred.get("items"):
            # Draw one item from the suite, fixed for this group from here
            # on — predict_example_json holds the chosen index.
            predict_example = {"prediction_item": random.randrange(len(pred["items"]))}
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
    if membership is None and not is_class_staff(user, group.klass):
        return jsonify(error="not a member of this group"), 403

    error = _worksheet_for_group_or_error(group, worksheet_id, user)
    if error:
        return error

    if membership is not None:
        membership.last_seen_at = utcnow()
        db.session.commit()

    progress = _get_or_create_progress(group, worksheet_id)
    question = serializers.current_question(worksheet_id, progress.current_question_index)
    state = _get_or_create_state(group, question) if question is not None else None

    if question is not None:
        # Self-healing: if the current typist has gone inactive (closed
        # the tab, etc) since the last poll — by anyone in the group —
        # hand the pen to someone else rather than stranding the group.
        typist_service.reassign_if_stale(progress, group_id)

    return jsonify(**serializers.build_group_state(group, progress, user, state))


@groups_bp.get("/<int:group_id>/history")
@login_required
def get_group_history(group_id):
    """Every published discussion this group has done in its class, for
    both its own students and its TA — a member of the group, or the
    section's TA (or an admin), but not anyone else.
    """
    group = _load_group(group_id)
    if group is None:
        return jsonify(error="group not found"), 404

    user = get_current_user()
    if _membership(group_id, user.id) is None:
        error = require_class_access(user, group.klass)
        if error:
            return error

    return jsonify(history=serializers.build_group_history(group))


@groups_bp.get("/<int:group_id>/worksheets/<int:worksheet_id>/work")
@login_required
def get_group_work(group_id, worksheet_id):
    """Read-only replay of this group's submitted code on one assignment —
    the "View work" link on a student's My Assignments page. Same access
    as group history: a member of the group, or the section's TA (or an
    admin), but not anyone else.
    """
    group = _load_group(group_id)
    if group is None:
        return jsonify(error="group not found"), 404

    user = get_current_user()
    if _membership(group_id, user.id) is None:
        error = require_class_access(user, group.klass)
        if error:
            return error

    error = _worksheet_for_group_or_error(group, worksheet_id, user)
    if error:
        return error

    return jsonify(**serializers.build_group_work(group, worksheet_id, user))


@groups_bp.put("/<int:group_id>/name")
@login_required
def rename_group(group_id):
    """Any current member can (re)name the group — it's shown at the top of
    the worksheet. Last write wins, mirroring the shared code editor."""
    group = _load_group(group_id)
    if group is None:
        return jsonify(error="group not found"), 404

    user = get_current_user()
    if _membership(group_id, user.id) is None:
        return jsonify(error="not a member of this group"), 403

    name = ((request.get_json(silent=True) or {}).get("name") or "").strip()
    if not name:
        return jsonify(error="a name is required"), 400
    group.name = name[:80]
    db.session.commit()
    return jsonify(ok=True, name=group.name)


@groups_bp.post("/<int:group_id>/worksheets/<int:worksheet_id>/questions/<int:question_id>/practice-run")
@login_required
def practice_run(group_id, worksheet_id, question_id):
    """Re-run tests against an already-unlocked question — personal
    practice only, whether that question is on a fully completed
    assignment (the History page's "View work") or is just an earlier
    question on one still in progress (the live worksheet page's "view a
    previous question" navigation — the group's shared position doesn't
    move). Includes the same prediction quiz as the live flow when a
    `prediction` is given (optional here, unlike the live route, since a
    plain re-run without one is still useful). Doesn't touch the group's
    real progress/typist/cooldown state: source="practice" is excluded
    from has_passing_shared_run and the group's shared last-run display,
    same as a scratch-editor run.
    """
    group = _load_group(group_id)
    if group is None:
        return jsonify(error="group not found"), 404

    user = get_current_user()
    if _membership(group_id, user.id) is None:
        return jsonify(error="not a member of this group"), 403

    error = _worksheet_for_group_or_error(group, worksheet_id, user)
    if error:
        return error

    question = Question.query.filter_by(id=question_id, worksheet_id=worksheet_id).first()
    if question is None:
        return jsonify(error="question not found"), 404
    if question.grading_mode == "discussion":
        return jsonify(error="this question has no autograder"), 400

    progress = GroupAssignmentProgress.query.filter_by(group_id=group_id, worksheet_id=worksheet_id).first()
    unlocked_index = progress.current_question_index if progress is not None else 0
    if question.order_index > unlocked_index:
        return jsonify(error="this question hasn't been unlocked yet"), 403

    data = request.get_json(silent=True) or {}
    code = data.get("code")
    if not code or not code.strip():
        return jsonify(error="code is required"), 400

    if not grader_cooldown_service.try_acquire(user):
        return (
            jsonify(
                error="cooldown active",
                remaining_seconds=grader_cooldown_service.remaining_seconds(user),
                cooldown_seconds=grader_cooldown_service.cooldown_seconds_for(user),
            ),
            429,
        )

    prediction = (data.get("prediction") or "").strip()
    predict_call = None
    if prediction:
        state = _get_or_create_state(group, question)
        if state.predict_example_json:
            predict_call = json.loads(state.predict_example_json).get("call")

    test_run = TestRun(
        group_id=group.id,
        question_id=question.id,
        user_id=user.id,
        source="practice",
        prediction_text=prediction,
        code_snapshot=code,
        status="pending",
    )
    db.session.add(test_run)
    db.session.commit()

    grading_queue_service.enqueue_grading_job(
        test_run.id, predict_call, prediction or None, grader_cooldown_service.cooldown_seconds_for(user)
    )

    return jsonify(test_run_id=test_run.id, status="pending"), 202


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
    error = _worksheet_for_group_or_error(group, worksheet_id, user)
    if error:
        return error

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


@groups_bp.put("/<int:group_id>/scratch-code")
@login_required
def update_scratch_code(group_id):
    """Personal, non-collaborative code — any member can edit their own
    regardless of who's typist. Persisted server-side (see ScratchCode's
    docstring) rather than only in browser localStorage, specifically so
    it's still there later: on the History page, or when browsing back to
    an earlier unlocked question mid-assignment.
    """
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

    error = _worksheet_for_group_or_error(group, worksheet_id, user)
    if error:
        return error

    progress = _get_or_create_progress(group, worksheet_id)
    question = serializers.current_question(worksheet_id, progress.current_question_index)
    if question is None:
        return jsonify(error="worksheet already completed"), 409

    scratch = ScratchCode.query.filter_by(group_id=group_id, question_id=question.id, user_id=user.id).first()
    if scratch is None:
        scratch = ScratchCode(group_id=group_id, question_id=question.id, user_id=user.id)
        db.session.add(scratch)
    scratch.code = data.get("code", "")
    scratch.updated_at = utcnow()
    db.session.commit()
    return jsonify(ok=True)


@groups_bp.post("/<int:group_id>/typist/give-up")
@login_required
def give_up_typist_route(group_id):
    """The current typist voluntarily releases the pen; it's randomly
    reassigned to another active group member (see services/typist.py).
    There's no more manual "claim" — the pen is always assigned for you,
    either when a new question starts or here.
    """
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

    error = _worksheet_for_group_or_error(group, worksheet_id, user)
    if error:
        return error

    if GroupMembership.query.filter_by(group_id=group_id).count() <= 1:
        return jsonify(error="you're the only person in this group — there's no one to give the pen to"), 409

    progress = _get_or_create_progress(group, worksheet_id)
    if typist_service.give_up_typist(progress, group_id, user.id):
        return jsonify(ok=True)

    return jsonify(error="you are not the current typist"), 409


@groups_bp.post("/<int:group_id>/leave")
@login_required
def leave_group_route(group_id):
    """Fired from StudentWorksheetPage on unmount when navigating away
    in-app — marks the caller inactive immediately (rather than waiting out
    the normal stale-poll timeout) and hands off the pen right away if they
    were holding it. Best-effort: a closed tab or refresh can't reliably
    fire this at all (no beacon — see Config.TYPIST_STALE_SECONDS' own
    fallback for that case), so this never needs to be load-bearing.
    """
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

    error = _worksheet_for_group_or_error(group, worksheet_id, user)
    if error:
        return error

    progress = _get_or_create_progress(group, worksheet_id)
    typist_service.leave(progress, group_id, user.id)
    return jsonify(ok=True)


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
    error = _worksheet_for_group_or_error(group, worksheet_id, user)
    if error:
        return error

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

    error = _worksheet_for_group_or_error(group, worksheet_id, user)
    if error:
        return error

    progress = _get_or_create_progress(group, worksheet_id)

    # Reviewing an earlier, already-unlocked question (WorkBrowserPage, or
    # StudentWorksheetPage's "browse a previous question" mode) should let
    # you change how you felt about *that* question, not just the group's
    # current one — so an explicit question_id targets any question the
    # group has already reached. Omitting it keeps the original behavior
    # (rate whatever's current), which is all the live worksheet page needs
    # for its in-focus question.
    question_id = data.get("question_id")
    if question_id is not None:
        question = Question.query.filter_by(id=question_id, worksheet_id=worksheet_id).first()
        if question is None or question.order_index > progress.current_question_index:
            return jsonify(error="question not found or not yet unlocked"), 404
    else:
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


@groups_bp.post("/<int:group_id>/worksheets/<int:worksheet_id>/questions/<int:question_id>/response")
@login_required
def submit_response(group_id, worksheet_id, question_id):
    """The group's shared answer to a non-code question (multiple choice,
    dropdown, fill-in-the-blank, short answer, plain text, counterexample).
    One row per (group, question) — any member submits or edits it, last
    write wins, mirroring the shared code editor. For auto-checkable types a
    correct answer here is what gates advancing (server/services/advance.py).
    A 'counterexample' answer is graded synchronously in the sandbox.
    """
    group = _load_group(group_id)
    if group is None:
        return jsonify(error="group not found"), 404

    user = get_current_user()
    if _membership(group_id, user.id) is None:
        return jsonify(error="not a member of this group"), 403

    error = _worksheet_for_group_or_error(group, worksheet_id, user)
    if error:
        return error

    question = Question.query.filter_by(id=question_id, worksheet_id=worksheet_id).first()
    if question is None:
        return jsonify(error="question not found"), 404
    if (question.problem_type or "coding") == "coding":
        return jsonify(error="this question is answered with code, not a response"), 400

    progress = GroupAssignmentProgress.query.filter_by(group_id=group_id, worksheet_id=worksheet_id).first()
    unlocked_index = progress.current_question_index if progress is not None else 0
    if question.order_index > unlocked_index:
        return jsonify(error="this question hasn't been unlocked yet"), 403

    data = request.get_json(silent=True) or {}
    response = data.get("response")

    if (question.problem_type or "coding") == "counterexample":
        is_correct, ce_error = counterexample_grading.grade(question, response)
        if ce_error:
            return jsonify(error=ce_error), 400
    else:
        is_correct = response_grading.check_response(question, response)

    row = QuestionResponse.query.filter_by(group_id=group.id, question_id=question.id).first()
    if row is None:
        row = QuestionResponse(group_id=group.id, question_id=question.id)
        db.session.add(row)
    row.user_id = user.id
    row.response_json = json.dumps(response)
    row.is_correct = is_correct
    row.created_at = utcnow()
    db.session.commit()

    return jsonify(ok=True, is_correct=is_correct)


@groups_bp.post("/<int:group_id>/worksheets/<int:worksheet_id>/questions/<int:question_id>/prediction")
@login_required
def submit_prediction(group_id, worksheet_id, question_id):
    """The group's shared answer to the optional prediction prompt on a
    question (Question.prediction_json). One row per (group, question).
    'output' mode is checked against the drawn item's sandbox-verified
    expected output (a pure string compare — the item was verified at save
    time); 'written' mode is just stored. A satisfied prediction gates
    advancing (server/services/advance.py).
    """
    group = _load_group(group_id)
    if group is None:
        return jsonify(error="group not found"), 404

    user = get_current_user()
    if _membership(group_id, user.id) is None:
        return jsonify(error="not a member of this group"), 403

    error = _worksheet_for_group_or_error(group, worksheet_id, user)
    if error:
        return error

    question = Question.query.filter_by(id=question_id, worksheet_id=worksheet_id).first()
    if question is None:
        return jsonify(error="question not found"), 404
    pred = _prediction_of(question)
    if not pred:
        return jsonify(error="this question has no prediction prompt"), 400

    progress = GroupAssignmentProgress.query.filter_by(group_id=group_id, worksheet_id=worksheet_id).first()
    unlocked_index = progress.current_question_index if progress is not None else 0
    if question.order_index > unlocked_index:
        return jsonify(error="this question hasn't been unlocked yet"), 403

    text = (request.get_json(silent=True) or {}).get("text") or ""

    is_correct = None
    if pred.get("mode") == "output":
        _get_or_create_state(group, question)  # ensure the item is drawn
        item = serializers.group_prediction_item(question, group.id)
        if item is not None:
            is_correct = response_grading.check_prediction(item["expected"], text)

    row = GroupPrediction.query.filter_by(group_id=group.id, question_id=question.id).first()
    if row is None:
        row = GroupPrediction(group_id=group.id, question_id=question.id)
        db.session.add(row)
    row.user_id = user.id
    row.prediction_text = text
    row.is_correct = is_correct
    row.created_at = utcnow()
    db.session.commit()

    return jsonify(ok=True, is_correct=is_correct)


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

    error = _worksheet_for_group_or_error(group, worksheet_id, user)
    if error:
        return error

    progress = _get_or_create_progress(group, worksheet_id)
    question = serializers.current_question(worksheet_id, progress.current_question_index)
    if question is None:
        return jsonify(error="worksheet already completed"), 409

    success, error = advance_service.try_advance(progress, group_id, question.id)
    if not success:
        return jsonify(error=error), 409

    return jsonify(ok=True)


@groups_bp.post("/<int:group_id>/advance/force")
@login_required
def force_advance(group_id):
    """Student-side escape hatch: any group member can skip the ratings
    requirement (unlike /advance above) — e.g. a member who crashed and
    can't come back to rate is otherwise an unbreakable deadlock (see
    services/advance.py:all_members_rated, no timeout by design). The tests
    still have to actually pass (advance_service.try_advance enforces that
    regardless of `force`) — this skips waiting on a missing person, not
    the assignment itself. The frontend gates this behind a confirm dialog;
    a group of one is rejected outright below, since there's no "someone
    else" who could be the one stuck.
    """
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

    if GroupMembership.query.filter_by(group_id=group_id).count() <= 1:
        return jsonify(error="you're the only person in this group — just rate and pass the tests normally"), 409

    error = _worksheet_for_group_or_error(group, worksheet_id, user)
    if error:
        return error

    progress = _get_or_create_progress(group, worksheet_id)
    question = serializers.current_question(worksheet_id, progress.current_question_index)
    if question is None:
        return jsonify(error="worksheet already completed"), 409

    success, error = advance_service.try_advance(progress, group_id, question.id, force=True)
    if not success:
        return jsonify(error=error), 409

    return jsonify(ok=True)


@groups_bp.get("/<int:group_id>/solution")
@role_required("ta")
def get_solution(group_id):
    group = _load_group(group_id)
    if group is None:
        return jsonify(error="group not found"), 404
    error = require_class_access(get_current_user(), group.klass)
    if error:
        return error

    worksheet_id = _worksheet_id_from_args()
    if worksheet_id is None:
        return jsonify(error="worksheet_id query param is required"), 400

    error = _worksheet_for_group_or_error(group, worksheet_id, get_current_user())
    if error:
        return error

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

    error = _worksheet_for_group_or_error(group, worksheet_id, user)
    if error:
        return error

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

    # The inline "predict before you run" quiz is retired — the optional
    # prediction prompt has its own submit endpoint now.
    prediction = (data.get("prediction") or "").strip()

    if not grader_cooldown_service.try_acquire(user):
        return (
            jsonify(
                error="cooldown active",
                remaining_seconds=grader_cooldown_service.remaining_seconds(user),
                cooldown_seconds=grader_cooldown_service.cooldown_seconds_for(user),
            ),
            429,
        )

    state = _get_or_create_state(group, question)
    predict_call = None
    if state.predict_example_json:
        predict_call = json.loads(state.predict_example_json).get("call")

    test_run = TestRun(
        group_id=group.id,
        question_id=question.id,
        user_id=user.id,
        source=source,
        prediction_text=prediction,
        code_snapshot=code,
        status="pending",
    )
    db.session.add(test_run)
    db.session.commit()

    # The actual Docker invocation happens out-of-process (`flask
    # grading-worker`, server/services/grading_jobs.py) so a slow/blocked
    # container doesn't tie up this web worker — see README "Grading
    # concurrency". The frontend polls GET .../run-tests/:id below for the
    # result, which lands in the exact same shape this endpoint used to
    # return synchronously.
    grading_queue_service.enqueue_grading_job(
        test_run.id, predict_call, prediction, grader_cooldown_service.cooldown_seconds_for(user)
    )

    return jsonify(test_run_id=test_run.id, status="pending"), 202


@groups_bp.get("/<int:group_id>/run-tests/<int:test_run_id>")
@login_required
def get_run_tests_result(group_id, test_run_id):
    user = get_current_user()
    if _membership(group_id, user.id) is None:
        return jsonify(error="not a member of this group"), 403

    test_run = TestRun.query.filter_by(id=test_run_id, group_id=group_id).first()
    if test_run is None:
        return jsonify(error="test run not found"), 404

    if test_run.status != "done":
        return jsonify(status="pending")

    results = json.loads(test_run.results_json)
    return jsonify(status="done", **results)


@groups_bp.get("/<int:group_id>/detail")
@role_required("ta")
def get_detail(group_id):
    group = _load_group(group_id)
    if group is None:
        return jsonify(error="group not found"), 404
    error = require_class_access(get_current_user(), group.klass)
    if error:
        return error

    worksheet_id = _worksheet_id_from_args()
    if worksheet_id is None:
        return jsonify(error="worksheet_id query param is required"), 400

    error = _worksheet_for_group_or_error(group, worksheet_id, get_current_user())
    if error:
        return error

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
    error = require_class_access(get_current_user(), group.klass)
    if error:
        return error

    data = request.get_json(silent=True) or {}
    worksheet_id = _worksheet_id_from_body(data)
    if worksheet_id is None:
        return jsonify(error="worksheet_id is required"), 400

    error = _worksheet_for_group_or_error(group, worksheet_id, get_current_user())
    if error:
        return error

    progress = _get_or_create_progress(group, worksheet_id)
    typist_service.release_typist(progress, group_id)
    return jsonify(ok=True)
