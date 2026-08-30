from server.extensions import db
from server.utils import utcnow


class Section(db.Model):
    """A grouping of students under a Class (e.g. one weekly discussion
    meeting) — kept as "Section" internally to minimize churn, and often
    called "class" in older UI copy/routes even though the actual class
    (course_name, assignments) now lives one level up on Class
    (server/models/klass.py). A Section holds a persistent roster of Groups
    (the small collaborative teams) and has its own TA, but no assignment
    content of its own — every Section under the same Class shares that
    Class's Worksheets.
    """

    __tablename__ = "sections"
    __table_args__ = (db.UniqueConstraint("class_id", "name"),)

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    # The one TA who owns this section — set by an admin (see
    # blueprints/admin.py:assign_section_ta), nullable until assigned.
    # A TA only sees/manages sections where this matches their own id; an
    # 'admin'-role user bypasses the check entirely (server/auth.py).
    ta_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    klass = db.relationship("Class", backref=db.backref("sections", lazy="dynamic"))
    groups = db.relationship("Group", backref="section", lazy="dynamic")
    ta = db.relationship("User", foreign_keys=[ta_user_id])


class SectionEnrollment(db.Model):
    """One row per (section, student email) — imported from the real
    enrollment roster (server/services/roster_import.py:import_enrollment_roster),
    independent of whether that student has ever logged in yet. Gates which
    section's groups a student may join (server/blueprints/sections.py) —
    it does not say which specific group within the section they end up in,
    only that they're allowed into some group there at all.
    """

    __tablename__ = "section_enrollments"
    __table_args__ = (db.UniqueConstraint("section_id", "student_email"),)

    id = db.Column(db.Integer, primary_key=True)
    section_id = db.Column(db.Integer, db.ForeignKey("sections.id"), nullable=False)
    student_email = db.Column(db.String(120), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utcnow)


class SectionCoTeacher(db.Model):
    """A TA sharing authority over a section they aren't the primary owner
    of — granted by anyone who already has authority over the section (the
    primary TA, an existing co-teacher, or an admin) via
    POST /api/sections/:id/co-teachers, keyed by the co-teacher's email
    (see server/services/roster_import.py:find_user_by_email). A co-teacher
    passes ta_owns_section (server/auth.py) exactly like the primary
    TA — same section on their own "Discussions" list, same access to its
    groups/worksheets/dashboard — the only thing Section.ta_user_id alone
    still determines is who counts as "the" TA for display purposes.
    """

    __tablename__ = "section_co_teachers"
    __table_args__ = (db.UniqueConstraint("section_id", "user_id"),)

    id = db.Column(db.Integer, primary_key=True)
    section_id = db.Column(db.Integer, db.ForeignKey("sections.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    user = db.relationship("User")
