from server.extensions import db
from server.utils import utcnow


class QuestionResponse(db.Model):
    """A group's shared answer to one non-code question (problem_type !=
    'coding'). Unlike Attempt (per-user prediction-quiz history) this is
    one row per (group, question) — any member submits or edits the
    group's single answer, last write wins, mirroring the shared code
    editor. is_correct is computed at submit time by
    server/services/response_grading.py (None for ungraded/display types).
    A correct row here is what gates advancing past an auto-checkable
    question (server/services/advance.py).
    """

    __tablename__ = "question_responses"
    __table_args__ = (db.UniqueConstraint("group_id", "question_id"),)

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    # The member who last submitted/edited the group's answer.
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    # JSON-in-Text: the student's raw answer, shape depends on problem_type
    # (list of selected option indices, list of blank strings, a string...).
    response_json = db.Column(db.Text, nullable=True)
    is_correct = db.Column(db.Boolean, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, index=True)

    user = db.relationship("User")
