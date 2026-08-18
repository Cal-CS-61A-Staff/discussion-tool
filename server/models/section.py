from server.extensions import db
from server.utils import utcnow


class Section(db.Model):
    """A class (kept as "Section" internally to minimize churn — "class" in
    UI copy and routes). Holds many Worksheets (assignments) over time and a
    persistent roster of Groups shared across all of them.
    """

    __tablename__ = "sections"

    id = db.Column(db.Integer, primary_key=True)
    course_name = db.Column(db.String(40), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    groups = db.relationship("Group", backref="section", lazy="dynamic")
    worksheets = db.relationship("Worksheet", backref="section", lazy="dynamic")
