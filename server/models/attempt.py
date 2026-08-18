from server.extensions import db
from server.utils import utcnow


class Attempt(db.Model):
    __tablename__ = "attempts"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    prediction_text = db.Column(db.Text, nullable=False)
    is_match = db.Column(db.Boolean, nullable=False)
    code_snapshot = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow, index=True)

    user = db.relationship("User")
