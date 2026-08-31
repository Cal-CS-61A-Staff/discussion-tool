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
    # TA/admin-toggled (not inferred from dates — there's no term/semester
    # concept in this app) — drives the Home page's Active/Past split.
    is_archived = db.Column(db.Boolean, default=False, nullable=False)


class ClassEnrollment(db.Model):
    """One row per (class, student email) — the course roster. Added by any
    TA/admin on the class (single email, or a `Email, Name` CSV bulk
    import — server/services/roster_import.py), independent of whether that
    student has logged in yet.

    Gates group joining course-wide (server/blueprints/sections.py:
    _enrollment_blocks_join): a rostered student may join a group under ANY
    section of this class — enrollment no longer says which section they're
    in, only that they belong to the course. A class with no roster rows at
    all stays open to anyone, same as before this existed. Replaced the old
    per-section SectionEnrollment.
    """

    __tablename__ = "class_enrollments"
    __table_args__ = (db.UniqueConstraint("class_id", "student_email"),)

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    student_email = db.Column(db.String(120), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utcnow)
