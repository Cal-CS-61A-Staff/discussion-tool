"""The retention job: snapshot participation to CSV, then hard-delete any
group idle past the TTL (server/services/retention.py)."""

import csv
import os
from datetime import timedelta

from server.extensions import db
from server.models.group import (
    Group,
    GroupAssignmentProgress,
    GroupMembership,
    GroupQuestionState,
)
from server.models.rating import Rating
from server.models.test_run import TestRun
from server.models.worksheet import Question, Worksheet
from server.services import retention
from server.tests.conftest import make_class
from server.utils import utcnow


def _seed(app, idle_days):
    klass = make_class("CS 61A")
    worksheet = Worksheet(class_id=klass.id, slug="disc-1", title="Discussion 1", is_published=True)
    db.session.add(worksheet)
    db.session.flush()
    q = Question(worksheet_id=worksheet.id, order_index=0, title="Q1", prompt="p")
    db.session.add(q)
    db.session.flush()

    group = Group(
        class_id=klass.id,
        number=3,
        name="Group 3",
        last_activity_at=utcnow() - timedelta(days=idle_days),
    )
    db.session.add(group)
    db.session.flush()
    db.session.add(
        GroupMembership(group_id=group.id, participant_key="p1", participant_name="Robin")
    )
    db.session.add(GroupAssignmentProgress(group_id=group.id, worksheet_id=worksheet.id, current_question_index=1))
    db.session.add(GroupQuestionState(group_id=group.id, question_id=q.id, code="x"))
    db.session.add(Rating(group_id=group.id, question_id=q.id, participant_key="p1", value=4))
    db.session.add(
        TestRun(
            group_id=group.id,
            question_id=q.id,
            participant_key="p1",
            source="shared",
            prediction_text="",
            code_snapshot="x",
            status="done",
            passed_count=1,
            total_count=1,
            results_json="{}",
        )
    )
    db.session.commit()
    return klass, worksheet, group


def test_snapshot_writes_a_csv_with_the_expected_columns(app, tmp_path):
    app.config["RETENTION_SNAPSHOT_DIR"] = str(tmp_path)
    from server.config import Config

    Config.RETENTION_SNAPSHOT_DIR = str(tmp_path)
    _klass, _worksheet, _group = _seed(app, idle_days=0)

    files, rows = retention.snapshot_participation()
    assert files == 1 and rows == 1

    csv_path = next(tmp_path.glob("**/*.csv"))
    with open(csv_path) as f:
        row = next(csv.DictReader(f))
    assert row["participant_name"] == "Robin"
    assert row["group_number"] == "3"
    assert row["completed"] == "yes"
    assert row["questions_total"] == "1"


def test_purge_deletes_stale_groups_and_all_children(app, tmp_path):
    from server.config import Config

    Config.RETENTION_SNAPSHOT_DIR = str(tmp_path)
    Config.SESSION_DATA_TTL_DAYS = 14

    _klass, _worksheet, stale = _seed(app, idle_days=30)
    stale_id = stale.id

    # A second, fresh group survives.
    fresh = Group(class_id=stale.class_id, number=9, name="Group 9", last_activity_at=utcnow())
    db.session.add(fresh)
    db.session.commit()
    fresh_id = fresh.id

    summary = retention.run()
    assert summary["groups_purged"] == 1

    assert db.session.get(Group, stale_id) is None
    assert GroupMembership.query.filter_by(group_id=stale_id).count() == 0
    assert Rating.query.filter_by(group_id=stale_id).count() == 0
    assert TestRun.query.filter_by(group_id=stale_id).count() == 0
    assert GroupAssignmentProgress.query.filter_by(group_id=stale_id).count() == 0
    assert db.session.get(Group, fresh_id) is not None


def test_participation_csv_download_is_staff_only(app, client, db):
    from server.config import Config
    from server.models.user import User
    from server.tests.conftest import add_member, login_as

    Config.RETENTION_SNAPSHOT_DIR = os.path.join(str(app.config["RETENTION_SNAPSHOT_DIR"]))
    klass, worksheet, _group = _seed(app, idle_days=0)

    staff = User(display_name="TA", role="student")
    db.session.add(staff)
    db.session.flush()
    add_member(staff, klass, "staff")
    db.session.commit()

    assert client.get(f"/api/worksheets/{worksheet.id}/participation.csv").status_code in (401, 403)

    login_as(client, staff)
    resp = client.get(f"/api/worksheets/{worksheet.id}/participation.csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.content_type
    assert b"Robin" in resp.data
