from server.extensions import db
from server.utils import utcnow


class Section(db.Model):
    """A "Room": an admin-configured slot in a Class's schedule — a name
    (e.g. "R 2:00 PM (VLSB 2050)"), the set of group **numbers** assigned
    to that room, and the staff member who runs it (+ optional
    co-teachers). Kept as "Section" internally to minimize churn.

    A Room no longer owns Groups or gates anything students see. Groups
    are class-scoped now (server/models/group.py) and students reach them
    by typing a number, not by picking a room. `assigned_numbers` seeds a
    TA's dashboard watch list (server/models/ta_watch.py); `ta_user_id` /
    co-teachers just record who runs the room, for that seeding and for
    display.
    """

    __tablename__ = "sections"
    __table_args__ = (db.UniqueConstraint("class_id", "name"),)

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    # Compact spec of the group numbers this room covers, e.g. "1-8,12".
    # Parsed by server/services/number_spec.py. Seeds the room's staff
    # member's dashboard watch list on first visit.
    assigned_numbers = db.Column(db.String(200), nullable=False, default="")
    created_at = db.Column(db.DateTime, default=utcnow)
    # The staff member who runs this room — set by staff/admin (see
    # blueprints/admin.py:assign_section_ta). Must have a 'staff'
    # ClassMembership for this class. Display + watch-seed only; it no
    # longer grants access on its own (that's the ClassMembership).
    ta_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    klass = db.relationship("Class", backref=db.backref("sections", lazy="dynamic"))
    ta = db.relationship("User", foreign_keys=[ta_user_id])


class SectionCoTeacher(db.Model):
    """An additional staff member who also runs a room — they get that
    room's `assigned_numbers` folded into their dashboard watch-list seed,
    same as the primary `ta_user_id`. Granted by anyone with staff access
    to the class (or an admin) by email
    (server/services/roster_import.py:find_user_by_email).

    Access to the class itself comes from the person's 'staff'
    ClassMembership, not this row — this only records room assignment.
    """

    __tablename__ = "section_co_teachers"
    __table_args__ = (db.UniqueConstraint("section_id", "user_id"),)

    id = db.Column(db.Integer, primary_key=True)
    section_id = db.Column(db.Integer, db.ForeignKey("sections.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    user = db.relationship("User")
