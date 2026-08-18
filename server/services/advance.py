"""Advancing a group to the next question on one assignment.

Advancing requires two things to both be true: (1) everyone in the group
has rated the current question, and (2) the group has at least one
successful "Run tests" against the shared editor — all test cases passing
*and* the prediction-quiz guess correct — for this question. Once both
hold, a compare-and-swap UPDATE on the group's
GroupAssignmentProgress.current_question_index ensures that if two "Next
question" clicks race through the checks at the same time, only one of
them actually advances.
"""

import json

from sqlalchemy import update

from server.extensions import db
from server.models.group import GroupAssignmentProgress, GroupMembership
from server.models.rating import Rating
from server.models.test_run import TestRun
from server.services import typist as typist_service
from server.utils import utcnow


def all_members_rated(group_id, question_id):
    member_count = GroupMembership.query.filter_by(group_id=group_id).count()
    rated_count = Rating.query.filter_by(group_id=group_id, question_id=question_id).count()
    return member_count > 0 and rated_count >= member_count


def has_passing_shared_run(group_id, question_id):
    """True if the group has ever submitted a "Run tests" against the
    shared editor for this question where every test case passed *and* the
    prediction-quiz guess was correct. Scratch-editor runs don't count —
    those are personal practice, not the group's official attempt.
    """
    runs = TestRun.query.filter_by(group_id=group_id, question_id=question_id, source="shared").all()
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


def ready_to_advance(group_id, question_id):
    return all_members_rated(group_id, question_id) and has_passing_shared_run(group_id, question_id)


def try_advance(progress, group_id, question_id):
    """Advance `progress` (a GroupAssignmentProgress row) to the next
    question if the group is ready (see ready_to_advance).

    Returns (success, error_message_or_None).
    """
    if not all_members_rated(group_id, question_id):
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


def try_go_back(progress, group_id):
    """Step back one question. No readiness gate — revisiting a previous
    question for review/discussion doesn't require re-earning it, and
    ratings/test-run history for both questions are untouched (so
    re-advancing afterward doesn't require redoing anything already done).
    Same guarded-CAS shape as try_advance so concurrent clicks don't
    double-decrement.
    """
    if progress.current_question_index <= 0:
        return False, "already at the first question"

    expected_index = progress.current_question_index
    result = db.session.execute(
        update(GroupAssignmentProgress)
        .where(GroupAssignmentProgress.id == progress.id, GroupAssignmentProgress.current_question_index == expected_index)
        .values(current_question_index=GroupAssignmentProgress.current_question_index - 1, question_started_at=utcnow())
    )
    db.session.commit()
    if result.rowcount == 0:
        return False, "group state changed, try again"

    progress.current_question_index = expected_index - 1
    typist_service.assign_random_typist(progress, group_id)
    return True, None
