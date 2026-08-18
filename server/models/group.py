from server.extensions import db
from server.utils import utcnow


class Group(db.Model):
    """A roster group scoped to a class (Section), not to any one
    assignment — it persists across every Worksheet in that class. Per-
    assignment mutable state (current question, typist, cooldown) lives on
    GroupAssignmentProgress instead, one row per (group, worksheet).
    """

    __tablename__ = "groups"
    __table_args__ = (db.UniqueConstraint("section_id", "number"),)

    id = db.Column(db.Integer, primary_key=True)
    section_id = db.Column(db.Integer, db.ForeignKey("sections.id"), nullable=False)
    # Sequential per section (1, 2, 3...), TA-assigned. Nullable: a personal
    # is_individual group has no human-facing number (SQLite treats
    # multiple NULLs in a unique constraint as distinct, so this is safe).
    number = db.Column(db.Integer, nullable=True)
    name = db.Column(db.String(80), nullable=False)
    # Auto-provisioned personal group backing "work individually" — reuses
    # all the same group/typist/cooldown/rating machinery for a group of
    # one, rather than a parallel solo-mode code path.
    is_individual = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)


class GroupAssignmentProgress(db.Model):
    """Per-(group, worksheet) mutable state — where this group is on this
    particular assignment. Looked up/created lazily, mirroring
    GroupQuestionState's pattern (see
    server/blueprints/groups.py:_get_or_create_progress).
    """

    __tablename__ = "group_assignment_progress"
    __table_args__ = (db.UniqueConstraint("group_id", "worksheet_id"),)

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)
    worksheet_id = db.Column(db.Integer, db.ForeignKey("worksheets.id"), nullable=False)
    current_question_index = db.Column(db.Integer, default=0, nullable=False)
    question_started_at = db.Column(db.DateTime, default=utcnow)
    typist_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    typist_claimed_at = db.Column(db.DateTime, nullable=True)
    # Source of truth for the group-wide run cooldown, on this assignment.
    last_attempt_at = db.Column(db.DateTime, nullable=True)


class GroupMembership(db.Model):
    __tablename__ = "group_memberships"
    __table_args__ = (db.UniqueConstraint("group_id", "user_id"),)

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    # Bumped on every /state poll — doubles as a free heartbeat used to
    # auto-release an inactive typist (see services/typist.py).
    last_seen_at = db.Column(db.DateTime, default=utcnow)
    joined_at = db.Column(db.DateTime, default=utcnow)

    user = db.relationship("User")
    group = db.relationship("Group")


class GroupQuestionState(db.Model):
    __tablename__ = "group_question_states"
    __table_args__ = (db.UniqueConstraint("group_id", "question_id"),)

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    code = db.Column(db.Text, default="")
    # {call, expected} chosen once (server/services/predict_examples.py) and
    # reused for every poll/run so the whole group is quizzed on the same
    # call — see server/blueprints/groups.py:_get_or_create_state.
    predict_example_json = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)
