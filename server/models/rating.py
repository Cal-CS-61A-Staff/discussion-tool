from server.extensions import db
from server.utils import utcnow


class Rating(db.Model):
    __tablename__ = "ratings"
    __table_args__ = (db.UniqueConstraint("group_id", "question_id", "participant_key"),)

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    participant_key = db.Column(db.String(40), nullable=False, index=True)
    value = db.Column(db.Integer, nullable=False)  # 1-5
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)
