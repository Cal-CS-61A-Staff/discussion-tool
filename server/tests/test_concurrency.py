"""Exercises the guarded UPDATE...WHERE (DB-level CAS) logic in
services/typist.py, cooldown.py, and advance.py — the parts most likely
to have a subtle race bug, per the app's concurrency design.
"""

import json

from sqlalchemy.orm import Session

from server.extensions import db
from server.models.group import Group, GroupAssignmentProgress, GroupMembership, GroupQuestionState
from server.models.rating import Rating
from server.models.section import Section
from server.models.test_run import TestRun
from server.models.user import User
from server.models.worksheet import Question, Worksheet
from server.services import advance as advance_service
from server.services import cooldown as cooldown_service
from server.services import serializers
from server.services import typist as typist_service


def _add_passing_shared_run(group_id, question_id, user_id):
    """Advancing now also requires a successful "Run tests" against the
    shared editor (all tests passing + correct prediction) — see
    services/advance.py:has_passing_shared_run.
    """
    results = {"passed_count": 1, "total_count": 1, "prediction_feedback": {"is_match": True}}
    db.session.add(
        TestRun(
            group_id=group_id,
            question_id=question_id,
            user_id=user_id,
            source="shared",
            prediction_text="x",
            code_snapshot="code",
            passed_count=1,
            total_count=1,
            total_points=1,
            max_points=1,
            results_json=json.dumps(results),
        )
    )
    db.session.commit()


def _make_group_with_members(n=2):
    section = Section(course_name="C", name="S")
    db.session.add(section)
    db.session.flush()

    worksheet = Worksheet(section_id=section.id, slug="w1", title="W1")
    db.session.add(worksheet)
    db.session.flush()

    question = Question(worksheet_id=worksheet.id, order_index=0, title="Q1", prompt="p", expected_output="42")
    db.session.add(question)

    group = Group(section_id=section.id, number=1, name="G1")
    db.session.add(group)
    db.session.flush()

    progress = GroupAssignmentProgress(group_id=group.id, worksheet_id=worksheet.id)
    db.session.add(progress)
    db.session.flush()

    users = []
    for i in range(n):
        user = User(display_name=f"user{i}", role="student")
        db.session.add(user)
        db.session.flush()
        db.session.add(GroupMembership(group_id=group.id, user_id=user.id))
        users.append(user)
    db.session.commit()
    return group, progress, question, users


def test_typist_claim_race(app):
    group, progress, _question, users = _make_group_with_members(2)

    first = typist_service.claim_typist(progress, group.id, users[0].id)
    second = typist_service.claim_typist(progress, group.id, users[1].id)

    assert first is True
    assert second is False
    assert progress.typist_user_id == users[0].id


def test_typist_pass_only_by_current_typist(app):
    _group, progress, _question, users = _make_group_with_members(2)
    typist_service.claim_typist(progress, _group.id, users[0].id)

    # users[1] never had the pen, so trying to pass it away should fail.
    stolen = typist_service.pass_typist(progress, users[1].id, users[0].id)
    assert stolen is False

    handed_off = typist_service.pass_typist(progress, users[0].id, users[1].id)
    assert handed_off is True
    assert progress.typist_user_id == users[1].id


def test_cooldown_blocks_second_attempt_immediately(app):
    _group, progress, _question, _users = _make_group_with_members(1)

    first = cooldown_service.try_acquire(progress)
    second = cooldown_service.try_acquire(progress)

    assert first is True
    assert second is False
    assert cooldown_service.remaining_seconds(progress) > 0


def test_advance_requires_all_ratings(app):
    group, progress, question, users = _make_group_with_members(2)
    _add_passing_shared_run(group.id, question.id, users[0].id)

    ok, error = advance_service.try_advance(progress, group.id, question.id)
    assert ok is False
    assert error is not None
    assert progress.current_question_index == 0

    for user in users:
        db.session.add(Rating(group_id=group.id, question_id=question.id, user_id=user.id, value=4))
    db.session.commit()

    ok, error = advance_service.try_advance(progress, group.id, question.id)
    assert ok is True
    assert error is None
    assert progress.current_question_index == 1


def test_advance_requires_a_passing_run(app):
    group, progress, question, users = _make_group_with_members(1)
    db.session.add(Rating(group_id=group.id, question_id=question.id, user_id=users[0].id, value=5))
    db.session.commit()

    # Everyone has rated, but there's no successful "Run tests" yet.
    ok, error = advance_service.try_advance(progress, group.id, question.id)
    assert ok is False
    assert error is not None
    assert progress.current_question_index == 0

    _add_passing_shared_run(group.id, question.id, users[0].id)

    ok, error = advance_service.try_advance(progress, group.id, question.id)
    assert ok is True
    assert error is None
    assert progress.current_question_index == 1


def test_group_state_surfaces_last_shared_run_to_every_member(app):
    """Regression test: TestRun previously had no `user` relationship, so
    build_group_state 500'd (AttributeError) as soon as it tried to expose
    who ran the group's last shared test — the exact thing a non-typist
    member needs in order to see the typist's passing run without having
    run it themselves.
    """
    group, progress, question, users = _make_group_with_members(2)
    _add_passing_shared_run(group.id, question.id, users[0].id)

    state = GroupQuestionState(group_id=group.id, question_id=question.id, code="code")
    db.session.add(state)
    db.session.commit()

    # users[1] never ran anything — this is their own view.
    payload = serializers.build_group_state(group, progress, users[1], state)
    last_run = payload["last_shared_run"]
    assert last_run is not None
    assert last_run["by"] == users[0].display_name
    assert last_run["passed_count"] == 1


def test_advance_cannot_double_advance(app):
    group, progress, question, users = _make_group_with_members(1)
    db.session.add(Rating(group_id=group.id, question_id=question.id, user_id=users[0].id, value=5))
    db.session.commit()
    _add_passing_shared_run(group.id, question.id, users[0].id)

    # Simulate two concurrent requests that both loaded the progress row
    # (and so both observed current_question_index == 0) before either one
    # commits its advance. A second, independent ORM session stands in for
    # "the other request"'s stale read — reusing `progress` for both calls
    # would silently self-heal via SQLAlchemy's session-sync-on-update and
    # defeat the point of this test.
    stale_session = Session(bind=db.session.get_bind())
    progress_stale_view = stale_session.get(GroupAssignmentProgress, progress.id)

    first_ok, _ = advance_service.try_advance(progress, group.id, question.id)
    second_ok, second_error = advance_service.try_advance(progress_stale_view, group.id, question.id)

    assert first_ok is True
    assert second_ok is False
    assert second_error is not None
    assert progress.current_question_index == 1

    stale_session.close()
