"""Advancing a group to the next question on one assignment.

Advancing requires two things to both be true: (1) everyone *currently
present* in the group has rated the current question, and (2) the group
has at least one successful "Run tests" against the shared editor — all
test cases passing *and* the prediction-quiz guess correct — for this
question. Once both hold, a compare-and-swap UPDATE on the group's
GroupAssignmentProgress.current_question_index ensures that if two "Next
question" clicks race through the checks at the same time, only one of
them actually advances.

"Everyone" is presence-based (services/presence.py), not "everyone who
has ever joined" — a GroupMembership row is permanent, but a member who
crashed/left and isn't coming back shouldn't get to block the group
forever just by having once joined.
"""

import json

from sqlalchemy import update

from server.extensions import db
from server.models.group import GroupAssignmentProgress
from server.models.question_response import QuestionResponse
from server.models.rating import Rating
from server.models.test_run import TestRun
from server.models.worksheet import Question
from server.services import presence
from server.services import response_grading
from server.services import typist as typist_service
from server.utils import utcnow


def all_members_rated(group_id, question_id):
    member_count = presence.active_member_count(group_id)
    rated_count = Rating.query.filter_by(group_id=group_id, question_id=question_id).count()
    return member_count > 0 and rated_count >= member_count


def _has_correct_group_response(group_id, question_id):
    response = QuestionResponse.query.filter_by(group_id=group_id, question_id=question_id).first()
    return response is not None and response.is_correct is True


def has_passing_shared_run(group_id, question_id):
    """True if the group has ever submitted a "Run tests" against the
    shared editor for this question where every test case passed *and* the
    prediction-quiz guess was correct. Scratch-editor runs don't count —
    those are personal practice, not the group's official attempt.

    'discussion' questions have no code/autograder at all, so there's
    nothing to run — this is trivially satisfied for them, and advancing
    depends only on everyone having rated (see ready_to_advance).

    Non-code questions (problem_type != 'coding'): auto-checkable types
    (multiple choice, dropdown, fill-in-the-blank, graded short answer)
    need a correct shared group answer on record; display/ungraded types
    behave like 'discussion'.
    """
    question = Question.query.get(question_id)
    if question is not None and (question.problem_type or "coding") != "coding":
        if response_grading.is_auto_checkable(question):
            return _has_correct_group_response(group_id, question_id)
        return True
    if question is not None and question.grading_mode == "discussion":
        return True

    runs = TestRun.query.filter_by(group_id=group_id, question_id=question_id, source="shared", status="done").all()
    for run in runs:
        if run.total_count == 0 or run.passed_count != run.total_count:
            continue
        try:
            results = json.loads(run.results_json)
        except ValueError:
            continue
        feedback = results.get("prediction_feedback")
        if feedback and feedback.get("is_match"):
            return True
    return False


def has_ever_passed_tests(group_id, question_id):
    """True if the group's shared editor has ever gotten every test case to
    pass for this question — deliberately independent of the *latest*
    submission, so a group that passes once and keeps resubmitting to
    optimize their solution doesn't see their own progress/grade regress
    just because a later attempt happens to fail. Backs progress/grade
    *display* (build_group_history, build_group_work, worksheet_grades) —
    a weaker bar than has_passing_shared_run above (no prediction-match
    requirement), which gates advancing instead.

    For auto-checkable non-code questions this is "the group has a correct
    answer on record"; display/ungraded non-code types have no notion of
    passing and stay False (advancing past them counts as completed via
    the question index, not passed — same as 'discussion').
    """
    question = Question.query.get(question_id)
    if question is not None and (question.problem_type or "coding") != "coding":
        if response_grading.is_auto_checkable(question):
            return _has_correct_group_response(group_id, question_id)
        return False

    runs = TestRun.query.filter_by(group_id=group_id, question_id=question_id, source="shared", status="done").all()
    return any(run.total_count > 0 and run.passed_count == run.total_count for run in runs)


def ready_to_advance(group_id, question_id):
    return all_members_rated(group_id, question_id) and has_passing_shared_run(group_id, question_id)


def try_advance(progress, group_id, question_id, force=False):
    """Advance `progress` (a GroupAssignmentProgress row) to the next
    question if the group is ready (see ready_to_advance).

    `force=True` skips only the ratings check — the student-side escape
    hatch (POST .../advance/force in server/blueprints/groups.py) for a
    group stuck on a member who'll never rate (crashed, dropped the class);
    any member can trigger it after a confirm-are-you-sure step in the UI,
    since requiring unanimous agreement would defeat the point of an escape
    hatch for exactly the case where unanimity is unreachable. It does NOT
    skip the passing-run check — forcing past a question nobody's actually
    solved isn't an escape hatch, it's just skipping the assignment, so
    that requirement always holds regardless of `force`. The advance itself
    still goes through the same guarded UPDATE...WHERE below, so a
    double-advance race is still impossible either way.

    Returns (success, error_message_or_None).
    """
    if not force and not all_members_rated(group_id, question_id):
        return False, "not everyone has rated this question yet"
    if not has_passing_shared_run(group_id, question_id):
        return False, "the group hasn't passed the tests (and correctly predicted the output) yet"

    expected_index = progress.current_question_index
    result = db.session.execute(
        update(GroupAssignmentProgress)
        .where(GroupAssignmentProgress.id == progress.id, GroupAssignmentProgress.current_question_index == expected_index)
        .values(current_question_index=GroupAssignmentProgress.current_question_index + 1, question_started_at=utcnow())
    )
    db.session.commit()
    if result.rowcount == 0:
        return False, "group already advanced"

    progress.current_question_index = expected_index + 1
    # Every new question gets a fresh random typist rather than whoever
    # happened to hold the pen last — see services/typist.py.
    typist_service.assign_random_typist(progress, group_id)
    return True, None
