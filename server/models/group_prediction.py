from server.extensions import db
from server.utils import utcnow


class GroupPrediction(db.Model):
    """A group's shared answer to the optional prediction prompt on a
    question (Question.prediction_json). One row per (group, question) —
    any member submits or edits it, last write wins, like the shared code
    editor. Kept separate from QuestionResponse because a non-code question
    can carry both a content answer and a prediction answer.

    is_correct: for an 'output' prediction, whether the text matches the
    drawn item's sandbox-verified expected output; None for a 'written'
    reflection. A satisfied prediction gates advancing
    (server/services/advance.py).
    """

    __tablename__ = "group_predictions"
    __table_args__ = (db.UniqueConstraint("group_id", "question_id"),)

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    participant_key = db.Column(db.String(40), nullable=False)
    prediction_text = db.Column(db.Text, nullable=True)
    is_correct = db.Column(db.Boolean, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, index=True)
