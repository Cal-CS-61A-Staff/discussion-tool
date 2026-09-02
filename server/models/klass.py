from server.extensions import db
from server.utils import utcnow


class Class(db.Model):
    """The top-level course entity (e.g. "CS 61A") — has many Sections
    (each an admin-configured "Room": a name + a set of group numbers +
    the staff member who runs it — see server/models/section.py) and many
    Worksheets/assignments (server/models/worksheet.py), shared across
    every section under it.

    `join_code` is what scopes a student to a class: they enter it once
    (POST /api/classes/join) and get a ClassMembership row. There is no
    email roster anymore — see ClassMembership below.
    """

    __tablename__ = "classes"

    id = db.Column(db.Integer, primary_key=True)
    course_name = db.Column(db.String(40), nullable=False)
    # Short, human-typable code a student enters once to join the class.
    # Generated on create (server/utils.py:generate_join_code); unique so
    # POST /api/classes/join can resolve it to exactly one class.
    join_code = db.Column(db.String(12), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    # TA/admin-toggled (not inferred from dates — there's no term/semester
    # concept in this app) — drives the Home page's Active/Past split.
    is_archived = db.Column(db.Boolean, default=False, nullable=False)


class ClassMembership(db.Model):
    """One row per (user, class) — the per-class role. Replaces the old
    email-keyed ClassEnrollment: a user gains a 'student' membership by
    entering the class's join_code, and an existing staff member or admin
    can grant/raise someone to 'staff' for a class explicitly
    (server/blueprints/sections.py:add_class_staff).

    This is what makes "88C staff, 61A student at the same time" work —
    role is per class, not the global User.role (which now only
    distinguishes the out-of-band 'admin' super-user). See
    server/auth.py:is_class_staff / is_class_member.
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
