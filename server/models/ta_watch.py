from server.extensions import db
from server.utils import utcnow


class TaWatchedNumber(db.Model):
    """One group number a staff member has chosen to watch on a class's
    live dashboard. Seeded on first visit from the union of
    `assigned_numbers` across the rooms they run
    (server/blueprints/ta.py:get_watched_numbers), then freely
    added/removed by that TA.
    """

    __tablename__ = "ta_watched_numbers"
    __table_args__ = (db.UniqueConstraint("user_id", "class_id", "number"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    number = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
