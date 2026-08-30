"""Exercises the guarded UPDATE...WHERE (DB-level CAS) logic in
services/typist.py, cooldown.py, and advance.py — the parts most likely
to have a subtle race bug, per the app's concurrency design.
"""

import json
from datetime import timedelta

from sqlalchemy.orm import Session

from server.config import Config
from server.extensions import db
from server.models.group import Group, GroupAssignmentProgress, GroupMembership, GroupQuestionState, ScratchCode
from server.models.klass import Class
from server.models.rating import Rating
from server.models.section import Section
from server.models.test_run import TestRun
from server.models.user import User
from server.models.worksheet import Question, Worksheet
from server.services import advance as advance_service
from server.services import cooldown as cooldown_service
from server.services import serializers
from server.services import typist as typist_service
from server.utils import utcnow


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
            status="done",
            passed_count=1,
            total_count=1,
            results_json=json.dumps(results),
        )
    )
    db.session.commit()


def _make_group_with_members(n=2):
    klass = Class(course_name="C")
    db.session.add(klass)
    db.session.flush()

    section = Section(class_id=klass.id, name="S")
    db.session.add(section)
    db.session.flush()

    worksheet = Worksheet(class_id=klass.id, slug="w1", title="W1", is_published=True)
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


def test_assign_random_typist_picks_an_active_member(app):
    group, progress, _question, users = _make_group_with_members(3)

    chosen = typist_service.assign_random_typist(progress, group.id)

    assert chosen in [u.id for u in users]
    assert progress.typist_user_id == chosen
    assert progress.typist_claimed_at is not None


def test_assign_random_typist_prefers_active_over_inactive(app):
    group, progress, _question, users = _make_group_with_members(3)
    stale_cutoff = timedelta(seconds=Config.TYPIST_STALE_SECONDS + 30)
    # Everyone but users[0] looks like they've been gone a while.
    for u in users[1:]:
        GroupMembership.query.filter_by(group_id=group.id, user_id=u.id).update(
            {"last_seen_at": utcnow() - stale_cutoff}
        )
    db.session.commit()

    chosen = typist_service.assign_random_typist(progress, group.id)

    assert chosen == users[0].id


def test_give_up_typist_reassigns_to_someone_else(app):
    group, progress, _question, users = _make_group_with_members(3)
    typist_service.assign_random_typist(progress, group.id)
    first_typist = progress.typist_user_id

    ok = typist_service.give_up_typist(progress, group.id, first_typist)

    assert ok is True
    assert progress.typist_user_id != first_typist
    assert progress.typist_user_id in [u.id for u in users if u.id != first_typist]


def test_give_up_typist_rejects_non_typist(app):
    group, progress, _question, users = _make_group_with_members(2)
    typist_service.assign_random_typist(progress, group.id)
    non_typist = next(u for u in users if u.id != progress.typist_user_id)

    ok = typist_service.give_up_typist(progress, group.id, non_typist.id)

    assert ok is False


def test_give_up_typist_solo_group_keeps_the_pen(app):
    group, progress, _question, users = _make_group_with_members(1)
    typist_service.assign_random_typist(progress, group.id)

    ok = typist_service.give_up_typist(progress, group.id, users[0].id)

    assert ok is True
    assert progress.typist_user_id == users[0].id


def test_give_up_typist_route_rejects_when_only_member(app, client):
    """The HTTP route (not the service function tested above) is where the
    user-facing rejection lives — clicking "give up the pen" with nobody
    else to hand it to should error clearly, not silently no-op.
    """
    from server.tests.conftest import login_as

    group, progress, _question, users = _make_group_with_members(1)
    typist_service.assign_random_typist(progress, group.id)
    login_as(client, users[0])

    resp = client.post(
        f"/api/groups/{group.id}/typist/give-up",
        json={"worksheet_id": progress.worksheet_id},
    )

    assert resp.status_code == 409
    assert "only person" in resp.get_json()["error"]


def test_give_up_typist_route_succeeds_with_other_members(app, client):
    from server.tests.conftest import login_as

    group, progress, _question, users = _make_group_with_members(2)
    typist_service.assign_random_typist(progress, group.id)
    login_as(client, next(u for u in users if u.id == progress.typist_user_id))

    resp = client.post(
        f"/api/groups/{group.id}/typist/give-up",
        json={"worksheet_id": progress.worksheet_id},
    )

    assert resp.status_code == 200


def test_reassign_if_stale_hands_off_an_inactive_typists_pen(app):
    group, progress, _question, users = _make_group_with_members(2)
    progress.typist_user_id = users[0].id
    db.session.commit()
    stale_cutoff = timedelta(seconds=Config.TYPIST_STALE_SECONDS + 30)
    GroupMembership.query.filter_by(group_id=group.id, user_id=users[0].id).update(
        {"last_seen_at": utcnow() - stale_cutoff}
    )
    db.session.commit()

    typist_service.reassign_if_stale(progress, group.id)

    assert progress.typist_user_id == users[1].id


def test_reassign_if_stale_leaves_an_active_typist_alone(app):
    group, progress, _question, users = _make_group_with_members(2)
    progress.typist_user_id = users[0].id
    db.session.commit()

    typist_service.reassign_if_stale(progress, group.id)

    assert progress.typist_user_id == users[0].id


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


def test_try_advance_force_skips_readiness_checks(app):
    group, progress, question, _users = _make_group_with_members(2)
    # Nobody has rated and there's no passing run — the normal gate fails.
    ok, error = advance_service.try_advance(progress, group.id, question.id)
    assert ok is False

    ok, error = advance_service.try_advance(progress, group.id, question.id, force=True)
    assert ok is True
    assert error is None
    assert progress.current_question_index == 1


def test_force_advance_route_works_for_any_member_with_no_ratings(app, client):
    from server.tests.conftest import login_as

    group, progress, question, users = _make_group_with_members(2)
    login_as(client, users[0])

    resp = client.post(
        f"/api/groups/{group.id}/advance/force",
        json={"worksheet_id": progress.worksheet_id},
    )

    assert resp.status_code == 200
    db.session.refresh(progress)
    assert progress.current_question_index == 1


def test_remove_group_member_unsticks_a_stalled_advance(app, client):
    """The scenario this endpoint exists for: one member rated and passed
    the tests, the other is a "ghost" (crashed, dropped the class, whatever)
    who will never rate — all_members_rated blocks forever until a TA
    removes them, per server/services/advance.py.
    """
    from server.tests.conftest import login_as

    group, progress, question, users = _make_group_with_members(2)
    present, ghost = users
    db.session.add(Rating(group_id=group.id, question_id=question.id, user_id=present.id, value=4))
    db.session.commit()
    _add_passing_shared_run(group.id, question.id, present.id)

    # Still stuck: ghost hasn't rated, so all_members_rated needs 2 but has 1.
    ok, _ = advance_service.try_advance(progress, group.id, question.id)
    assert ok is False

    ta = User(display_name="TA", role="ta")
    db.session.add(ta)
    db.session.commit()
    group.section.ta_user_id = ta.id
    db.session.commit()
    login_as(client, ta)

    resp = client.delete(f"/api/groups/{group.id}/members/{ghost.id}")
    assert resp.status_code == 200
    assert GroupMembership.query.filter_by(group_id=group.id, user_id=ghost.id).first() is None

    ok, error = advance_service.try_advance(progress, group.id, question.id)
    assert ok is True, error
    assert progress.current_question_index == 1


def test_remove_group_member_rejects_removing_the_last_member(app, client):
    """Removing the last member would leave a 0-member group, which
    all_members_rated treats as permanently un-advanceable — the opposite
    of what this endpoint is for.
    """
    from server.tests.conftest import login_as

    group, _progress, _question, users = _make_group_with_members(1)
    ta = User(display_name="TA", role="ta")
    db.session.add(ta)
    db.session.commit()
    group.section.ta_user_id = ta.id
    db.session.commit()
    login_as(client, ta)

    resp = client.delete(f"/api/groups/{group.id}/members/{users[0].id}")

    assert resp.status_code == 409
    assert GroupMembership.query.filter_by(group_id=group.id, user_id=users[0].id).first() is not None


def test_all_members_rated_ignores_stale_members(app):
    """The presence redesign: a member who stopped polling /state (crashed,
    signed out, whatever) shouldn't count toward "everyone" — only whoever
    is actually active right now has to rate. See services/presence.py.
    """
    group, _progress, question, users = _make_group_with_members(2)
    present, gone = users
    GroupMembership.query.filter_by(group_id=group.id, user_id=gone.id).update(
        {"last_seen_at": utcnow() - timedelta(seconds=Config.TYPIST_STALE_SECONDS + 30)}
    )
    db.session.commit()

    db.session.add(Rating(group_id=group.id, question_id=question.id, user_id=present.id, value=5))
    db.session.commit()

    assert advance_service.all_members_rated(group.id, question.id) is True


def test_practice_run_route_allows_an_already_unlocked_earlier_question(app, client, monkeypatch):
    """practice-run used to require the *whole worksheet* to be completed —
    now it just requires the specific question to already be unlocked, so
    a group mid-assignment can revisit an earlier question without the
    group's own shared position moving (server/services/serializers.py:
    build_group_work, server/blueprints/groups.py:practice_run).
    """
    from server.tests.conftest import login_as

    group, progress, question_0, users = _make_group_with_members(1)
    question_1 = Question(worksheet_id=progress.worksheet_id, order_index=1, title="Q2", prompt="p2", expected_output="1")
    db.session.add(question_1)
    progress.current_question_index = 1  # group has moved on to question 1
    db.session.commit()

    monkeypatch.setattr(
        "server.blueprints.groups.grading_queue_service.enqueue_grading_job", lambda *a, **kw: None
    )
    login_as(client, users[0])

    resp = client.post(
        f"/api/groups/{group.id}/worksheets/{progress.worksheet_id}/questions/{question_0.id}/practice-run",
        json={"code": "def f(): return 1"},
    )

    assert resp.status_code == 202
    assert resp.get_json()["status"] == "pending"


def test_practice_run_route_rejects_a_not_yet_unlocked_question(app, client):
    from server.tests.conftest import login_as

    group, progress, question_0, users = _make_group_with_members(1)
    question_1 = Question(worksheet_id=progress.worksheet_id, order_index=1, title="Q2", prompt="p2", expected_output="1")
    db.session.add(question_1)
    db.session.commit()
    # progress.current_question_index is still 0 — question_1 isn't unlocked.

    login_as(client, users[0])

    resp = client.post(
        f"/api/groups/{group.id}/worksheets/{progress.worksheet_id}/questions/{question_1.id}/practice-run",
        json={"code": "def f(): return 1"},
    )

    assert resp.status_code == 403
    assert "hasn't been unlocked" in resp.get_json()["error"]


def test_build_group_work_excludes_locked_questions(app):
    group, progress, question_0, users = _make_group_with_members(1)
    question_1 = Question(worksheet_id=progress.worksheet_id, order_index=1, title="Q2", prompt="p2", expected_output="1")
    db.session.add(question_1)
    db.session.commit()
    # progress.current_question_index is 0 — only question_0 is unlocked.

    work = serializers.build_group_work(group, progress.worksheet_id, users[0])

    ids = [q["question_id"] for q in work["questions"]]
    assert question_0.id in ids
    assert question_1.id not in ids


def test_update_scratch_code_route_persists_per_user(app, client):
    from server.tests.conftest import login_as

    group, progress, question, users = _make_group_with_members(2)
    login_as(client, users[0])

    resp = client.put(
        f"/api/groups/{group.id}/scratch-code",
        json={"worksheet_id": progress.worksheet_id, "code": "def f(): return 1"},
    )
    assert resp.status_code == 200

    scratch = ScratchCode.query.filter_by(group_id=group.id, question_id=question.id, user_id=users[0].id).first()
    assert scratch is not None
    assert scratch.code == "def f(): return 1"

    # A groupmate's scratch code is independent, not overwritten.
    other = ScratchCode.query.filter_by(group_id=group.id, question_id=question.id, user_id=users[1].id).first()
    assert other is None


def test_group_state_includes_my_scratch_code(app):
    group, progress, question, users = _make_group_with_members(1)
    state = GroupQuestionState(group_id=group.id, question_id=question.id, code="")
    db.session.add(state)
    db.session.add(ScratchCode(group_id=group.id, question_id=question.id, user_id=users[0].id, code="scratch code"))
    db.session.commit()

    payload = serializers.build_group_state(group, progress, users[0], state)

    assert payload["my_scratch_code"] == "scratch code"


def test_build_group_work_includes_viewers_own_scratch_code(app):
    group, progress, question, users = _make_group_with_members(2)
    db.session.add(ScratchCode(group_id=group.id, question_id=question.id, user_id=users[0].id, code="mine"))
    db.session.commit()

    work_mine = serializers.build_group_work(group, progress.worksheet_id, users[0])
    work_theirs = serializers.build_group_work(group, progress.worksheet_id, users[1])

    assert work_mine["questions"][0]["scratch_code"] == "mine"
    assert work_theirs["questions"][0]["scratch_code"] is None


def test_go_back_route_removed(app, client):
    """Replaced by per-viewer navigation (build_group_work/practice-run) —
    the group's shared position no longer moves backward at all. 405, not
    404: the SPA catch-all route (server/app.py) matches any unmatched URL
    but only registers GET, so Werkzeug rejects the method before that
    view's own 404-for-/api/ logic ever runs.
    """
    from server.tests.conftest import login_as

    group, progress, _question, users = _make_group_with_members(1)
    login_as(client, users[0])

    resp = client.post(f"/api/groups/{group.id}/go-back", json={"worksheet_id": progress.worksheet_id})

    assert resp.status_code == 405


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


def test_group_state_includes_worksheet_title(app):
    """A group can have several worksheets in flight independently, each
    with its own typist — without a worksheet title in the payload, two
    members on *different* worksheets in the same group would see
    identically-labeled pages with no way to notice they're not actually
    looking at the same assignment (each would just see "Group N" and
    correctly believe they're the typist, for their own worksheet).
    """
    group, progress, question, users = _make_group_with_members(1)
    state = GroupQuestionState(group_id=group.id, question_id=question.id, code="code")
    db.session.add(state)
    db.session.commit()

    payload = serializers.build_group_state(group, progress, users[0], state)

    assert payload["worksheet_title"] == "W1"


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


def test_group_routes_reject_a_worksheet_from_a_different_class(app, client):
    """A student's group belongs to exactly one class — none of the routes
    that accept a client-supplied worksheet_id should let them use it with
    a worksheet from a *different* class, published or not. Without
    _worksheet_for_group_or_error (server/blueprints/groups.py), any of
    these would happily create progress against, view, or even run real
    code through the sandboxed grader against a totally unrelated
    worksheet, just by supplying its id.
    """
    from server.tests.conftest import login_as

    group, _progress, _question, users = _make_group_with_members(1)

    other_klass = Class(course_name="Other")
    db.session.add(other_klass)
    db.session.flush()
    foreign_worksheet = Worksheet(class_id=other_klass.id, slug="foreign", title="Foreign", is_published=True)
    db.session.add(foreign_worksheet)
    db.session.commit()

    login_as(client, users[0])

    resp = client.get(f"/api/groups/{group.id}/state?worksheet_id={foreign_worksheet.id}")
    assert resp.status_code == 404

    resp = client.post(
        f"/api/groups/{group.id}/run-tests",
        json={"worksheet_id": foreign_worksheet.id, "source": "scratch", "code": "x = 1", "prediction": "x"},
    )
    assert resp.status_code == 404

    resp = client.get(f"/api/groups/{group.id}/worksheets/{foreign_worksheet.id}/work")
    assert resp.status_code == 404

    resp = client.post(f"/api/groups/{group.id}/ratings", json={"worksheet_id": foreign_worksheet.id, "value": 5})
    assert resp.status_code == 404

    # Confirms it's really the class check (not something else rejecting
    # every request): the group's own, same-class worksheet still works.
    resp = client.get(f"/api/groups/{group.id}/state?worksheet_id={_progress.worksheet_id}")
    assert resp.status_code == 200
