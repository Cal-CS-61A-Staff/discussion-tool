from server.extensions import db
from server.utils import utcnow


class Group(db.Model):
    """A roster group scoped to a Class, not to any one assignment or room
    — it persists across every Worksheet in that class. Students land in
    one by typing its `number` on an assignment's join screen (Pensive
    style): everyone who types the same number in the same class is in the
    same group. Per-assignment mutable state (current question, typist,
    cooldown) lives on GroupAssignmentProgress, one row per (group,
    worksheet).
    """

    __tablename__ = "groups"
    __table_args__ = (db.UniqueConstraint("class_id", "number"),)

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    # The number a student types to join. Nullable: a personal
    # is_individual group has no number (SQLite/Postgres both treat
    # multiple NULLs in a unique constraint as distinct, so this is safe).
    number = db.Column(db.Integer, nullable=True)
    # Free-text label a group can give itself, shown at the top of the
    # worksheet — any member can set it (PUT /api/groups/:id/name).
    name = db.Column(db.String(80), nullable=False)
    # Auto-provisioned personal group backing "work individually" — reuses
    # all the same group/typist/cooldown/rating machinery for a group of
    # one, rather than a parallel solo-mode code path.
    is_individual = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    klass = db.relationship("Class")


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
    # auto-release an inactive typist (see services/typist.py) and to show
    # a TA who's currently logged into each watched number.
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


class ScratchCode(db.Model):
    """A student's own private practice code for one question — unlike
    GroupQuestionState.code (the group's shared, collaborative buffer),
    this is per-user, not per-group, and never visible to groupmates.
    Persisted server-side (not just browser localStorage) specifically so
    it survives being viewed later — on the History page's "View work" for
    a completed assignment, or when browsing back to an earlier unlocked
    question mid-assignment (server/services/serializers.py:
    build_group_work) — rather than vanishing the moment a different
    browser/device is used or site data is cleared.
    """

    __tablename__ = "scratch_codes"
    __table_args__ = (db.UniqueConstraint("group_id", "question_id", "user_id"),)

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    code = db.Column(db.Text, default="")
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)
