"""Retention: keep the database holding only TA-authored content.

Students are anonymous and every row they generate is transient. This
module, run daily from `flask retention-run`
(deploy/systemd/cs61a-retention.{service,timer}):

1. snapshots participation for every (class, worksheet) that has any
   activity, to a CSV a TA can download
   (GET /api/worksheets/<id>/participation.csv), then
2. hard-deletes any Group idle longer than
   Config.SESSION_DATA_TTL_DAYS, with all of its child rows.

The CSV is the durable participation record; nothing student-identifying
survives in the DB past the TTL.
"""

import csv
import os
import re
from datetime import timedelta

from server.config import Config
from server.extensions import db
from server.models.group import (
    Group,
    GroupAssignmentProgress,
    GroupMembership,
    GroupQuestionState,
    ScratchCode,
)
from server.models.group_prediction import GroupPrediction
from server.models.klass import Class
from server.models.question_response import QuestionResponse
from server.models.rating import Rating
from server.models.test_run import TestRun
from server.models.worksheet import Question, Worksheet
from server.services import advance as advance_service
from server.utils import utcnow

CSV_COLUMNS = [
    "class",
    "worksheet",
    "worksheet_id",
    "group_number",
    "group_name",
    "participant_name",
    "joined_at",
    "last_seen_at",
    "questions_passed",
    "questions_total",
    "completed",
    "completed_at",
    "snapshot_at",
]

# Child tables keyed by group_id, deleted before the Group itself.
_GROUP_CHILDREN = (
    GroupQuestionState,
    ScratchCode,
    TestRun,
    QuestionResponse,
    GroupPrediction,
    Rating,
    GroupAssignmentProgress,
    GroupMembership,
)


def _slug(text):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", (text or "").lower())).strip("-") or "x"


def participation_rows(worksheet):
    """One dict per (group, participant) for `worksheet` — the shape the
    CSV and the TA download endpoint both use."""
    total = Question.query.filter_by(worksheet_id=worksheet.id).count()
    question_ids = [q.id for q in Question.query.filter_by(worksheet_id=worksheet.id).all()]
    snapshot_at = utcnow().isoformat(timespec="seconds")
    rows = []

    progresses = GroupAssignmentProgress.query.filter_by(worksheet_id=worksheet.id).all()
    for progress in progresses:
        group = Group.query.get(progress.group_id)
        if group is None:
            continue
        completed = total > 0 and progress.current_question_index >= total
        passed = sum(
            1 for qid in question_ids if advance_service.has_ever_passed_tests(group.id, qid)
        )
        members = GroupMembership.query.filter_by(group_id=group.id).all() or [None]
        for m in members:
            rows.append(
                {
                    "class": worksheet.klass.course_name,
                    "worksheet": worksheet.title,
                    "worksheet_id": worksheet.id,
                    "group_number": group.number if group.number is not None else "",
                    "group_name": group.name,
                    "participant_name": m.participant_name if m else "",
                    "joined_at": m.joined_at.isoformat(timespec="seconds") if m and m.joined_at else "",
                    "last_seen_at": m.last_seen_at.isoformat(timespec="seconds") if m and m.last_seen_at else "",
                    "questions_passed": passed,
                    "questions_total": total,
                    "completed": "yes" if completed else "no",
                    "completed_at": (
                        progress.question_started_at.isoformat(timespec="seconds")
                        if completed and progress.question_started_at
                        else ""
                    ),
                    "snapshot_at": snapshot_at,
                }
            )
    return rows


def _write_csv(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def snapshot_participation():
    """Rewrite one CSV per (class, worksheet) that has any progress rows.
    Returns (files_written, total_rows)."""
    base = Config.RETENTION_SNAPSHOT_DIR
    files = rows_total = 0
    worksheet_ids = {p.worksheet_id for p in GroupAssignmentProgress.query.all()}
    for wid in worksheet_ids:
        worksheet = Worksheet.query.get(wid)
        if worksheet is None:
            continue
        rows = participation_rows(worksheet)
        if not rows:
            continue
        path = os.path.join(base, _slug(worksheet.klass.course_name), f"{_slug(worksheet.slug)}.csv")
        _write_csv(path, rows)
        files += 1
        rows_total += len(rows)
    return files, rows_total


def purge_stale(now=None):
    """Delete every Group (and its child rows) idle longer than the TTL.
    Returns the number of groups deleted."""
    now = now or utcnow()
    cutoff = now - timedelta(days=Config.SESSION_DATA_TTL_DAYS)
    stale = Group.query.filter(Group.last_activity_at < cutoff).all()
    if not stale:
        return 0
    group_ids = [g.id for g in stale]
    for model in _GROUP_CHILDREN:
        model.query.filter(model.group_id.in_(group_ids)).delete(synchronize_session=False)
    Group.query.filter(Group.id.in_(group_ids)).delete(synchronize_session=False)
    db.session.commit()
    return len(group_ids)


def run(snapshot_only=False):
    files, rows = snapshot_participation()
    purged = 0 if snapshot_only else purge_stale()
    return {"snapshots": files, "rows": rows, "groups_purged": purged}
