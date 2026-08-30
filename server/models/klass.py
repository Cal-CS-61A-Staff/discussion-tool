from server.extensions import db
from server.utils import utcnow


class Class(db.Model):
    """The top-level course entity (e.g. "CS 61A") — has many Sections
    (each just a roster/grouping of students with its own TA — see
    server/models/section.py) and many Worksheets/assignments
    (server/models/worksheet.py), shared across every section under it.
    Mirrors the real course structure: one course, several weekly
    discussion meetings (Sections) that all work the same assignments.
    """

    __tablename__ = "classes"

    id = db.Column(db.Integer, primary_key=True)
    course_name = db.Column(db.String(40), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
