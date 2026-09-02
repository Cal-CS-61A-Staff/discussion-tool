from server.extensions import db
from server.utils import utcnow


class Class(db.Model):
    """The top-level course entity (e.g. "CS 61A") — has many Sections
    (each an admin-configured "Room": a name + a set of group numbers +
    the staff member who runs it — see server/models/section.py) and many
    Worksheets/assignments (server/models/worksheet.py), shared across
    every section under it.

    Students have no relationship to a Class at all — they reach an
    assignment by its per-worksheet share link (Worksheet.share_code,
    server/blueprints/w.py) and are anonymous (server/participant.py).
    `join_code` is retained only as a stable per-class identifier shown to
    staff; it no longer gates anything.
    """

    __tablename__ = "classes"

    id = db.Column(db.Integer, primary_key=True)
    course_name = db.Column(db.String(40), nullable=False)
    # Legacy: was a student-typable join code. Kept (still generated on
    # create, still unique) as a stable staff-facing class identifier;
    # nothing resolves a student through it anymore.
    join_code = db.Column(db.String(12), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    # TA/admin-toggled (not inferred from dates — there's no term/semester
    # concept in this app) — drives the Home page's Active/Past split.
    is_archived = db.Column(db.Boolean, default=False, nullable=False)


class ClassMembership(db.Model):
    """Staff-only now — one row per (staff user, class), always
    role='staff'. Granted by an existing staff member or an admin
    (server/blueprints/sections.py:add_class_staff). Students have no
    membership of any kind. `role` is kept for the (unlikely) future need
    to distinguish staff tiers; the retention migration deleted every
    non-'staff' row. See server/auth.py:is_class_staff.
    """

    __tablename__ = "class_memberships"
    __table_args__ = (db.UniqueConstraint("user_id", "class_id"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    # 'student' | 'staff'
    role = db.Column(db.String(10), nullable=False, default="student")
    created_at = db.Column(db.DateTime, default=utcnow)

    user = db.relationship("User")
    klass = db.relationship("Class")
