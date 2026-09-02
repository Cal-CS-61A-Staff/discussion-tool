from flask import Blueprint, jsonify, request
from sqlalchemy import distinct, func

from server.auth import (
    get_current_user,
    login_required,
    require_class_access,
    require_section_access,
)
from server.extensions import db
from server.models.group import Group, GroupMembership
from server.models.klass import Class, ClassMembership
from server.models.section import Section, SectionCoTeacher
from server.models.user import User
from server.models.worksheet import Worksheet
from server.services.number_spec import parse_number_spec
from server.services.roster_import import _placeholder_display_name, find_user_by_email
from server.services.watch_list import set_watched_numbers, watched_numbers_for

sections_bp = Blueprint("sections", __name__)


@sections_bp.get("/classes")
@login_required
def list_classes():
    """Staff-only now — students have no accounts and reach an assignment
    by its share link, not a class list. A staff member sees the classes
    they staff; an admin sees every class.
    """
    user = get_current_user()
    staff_class_ids = {
        m.class_id for m in ClassMembership.query.filter_by(user_id=user.id, role="staff").all()
    }

    if user.role == "admin":
        classes = Class.query.all()
    elif staff_class_ids:
        classes = Class.query.filter(Class.id.in_(staff_class_ids)).all()
    else:
        classes = []

    return jsonify(classes=[_serialize_class(c, "staff") for c in classes])


@sections_bp.get("/classes/<int:class_id>/staff")
@login_required
def list_class_staff(class_id):
    """The class's staff roster — any staff member of the class, or an admin."""
    klass = Class.query.get_or_404(class_id)
    error = require_class_access(get_current_user(), klass)
    if error:
        return error
    rows = ClassMembership.query.filter_by(class_id=class_id, role="staff").all()
    return jsonify(staff=[_serialize_membership(m) for m in rows])


@sections_bp.post("/classes/<int:class_id>/staff")
@login_required
def add_class_staff(class_id):
    """Grant staff access to the class by email (found or created), the
    same identity key roster import and login use. Any existing staff
    member of the class, or an admin."""
    klass = Class.query.get_or_404(class_id)
    error = require_class_access(get_current_user(), klass)
    if error:
        return error

    email = ((request.get_json(silent=True) or {}).get("email") or "").strip().lower()
    if not email or "@" not in email:
        return jsonify(error="a valid email is required"), 400

    target = find_user_by_email(email)
    if target is None:
        target = User(display_name=_placeholder_display_name(email), role="student", email=email)
        db.session.add(target)
        db.session.flush()

    membership = ClassMembership.query.filter_by(user_id=target.id, class_id=class_id).first()
    if membership is None:
        db.session.add(ClassMembership(user_id=target.id, class_id=class_id, role="staff"))
    else:
        membership.role = "staff"
    db.session.commit()

    return jsonify(staff=[_serialize_membership(m) for m in ClassMembership.query.filter_by(class_id=class_id, role="staff").all()])


@sections_bp.delete("/classes/<int:class_id>/staff/<int:user_id>")
@login_required
def remove_class_staff(class_id, user_id):
    """Revoke a person's membership of the class entirely (they can
    re-join as a student with the code). Any staff member, or an admin."""
    klass = Class.query.get_or_404(class_id)
    error = require_class_access(get_current_user(), klass)
    if error:
        return error
    ClassMembership.query.filter_by(class_id=class_id, user_id=user_id).delete()
    # Also drop them from any room they ran, so a stale name doesn't linger.
    for section in Section.query.filter_by(class_id=class_id).all():
        if section.ta_user_id == user_id:
            section.ta_user_id = None
    SectionCoTeacher.query.filter(
        SectionCoTeacher.user_id == user_id,
        SectionCoTeacher.section_id.in_([s.id for s in Section.query.filter_by(class_id=class_id).all()]),
    ).delete(synchronize_session=False)
    db.session.commit()
    return jsonify(ok=True)


@sections_bp.get("/sections")
@login_required
def list_sections():
    """Rooms for classes the caller staffs (an admin sees every room).
    Students have no use for this — a room is staff-only config now."""
    user = get_current_user()
    if user.role == "admin":
        sections = Section.query.all()
    else:
        staff_class_ids = [
            m.class_id for m in ClassMembership.query.filter_by(user_id=user.id, role="staff").all()
        ]
        sections = Section.query.filter(Section.class_id.in_(staff_class_ids)).all() if staff_class_ids else []
    return jsonify(sections=[_serialize_section(s, user) for s in sections])


@sections_bp.get("/classes/<int:class_id>/worksheets")
@login_required
def class_worksheets(class_id):
    """Assignments in a class — staff/admin only (students reach an
    assignment by its share link). Drafts included."""
    klass = Class.query.get_or_404(class_id)
    error = require_class_access(get_current_user(), klass)
    if error:
        return error
    worksheets = Worksheet.query.filter_by(class_id=klass.id).order_by(Worksheet.created_at).all()
    return jsonify(worksheets=[_serialize_worksheet(w) for w in worksheets])


@sections_bp.get("/classes/<int:class_id>/watched-numbers")
@login_required
def get_watched_numbers(class_id):
    """The caller's live-dashboard watch list for this class (staff/admin);
    seeded from the rooms they run on first access."""
    klass = Class.query.get_or_404(class_id)
    error = require_class_access(get_current_user(), klass)
    if error:
        return error
    return jsonify(numbers=watched_numbers_for(get_current_user(), klass))


@sections_bp.put("/classes/<int:class_id>/watched-numbers")
@login_required
def put_watched_numbers(class_id):
    klass = Class.query.get_or_404(class_id)
    error = require_class_access(get_current_user(), klass)
    if error:
        return error
    raw = (request.get_json(silent=True) or {}).get("numbers") or []
    numbers = [int(n) for n in raw if str(n).lstrip("-").isdigit() and 1 <= int(n) <= 999]
    return jsonify(numbers=set_watched_numbers(get_current_user(), klass, numbers))


def _serialize_membership(membership):
    return {
        "user_id": membership.user.id,
        "display_name": membership.user.display_name,
        "email": membership.user.email,
        "role": membership.role,
    }


def _serialize_class(klass, my_role="staff"):
    # Live participant count — everyone with a current group membership in
    # this class. Transient (the retention job prunes it); shown for a
    # rough "who's here now" sense, not a roster.
    active_participants = (
        db.session.query(func.count(distinct(GroupMembership.participant_key)))
        .join(Group, Group.id == GroupMembership.group_id)
        .filter(Group.class_id == klass.id)
        .scalar()
    ) or 0
    return {
        "id": klass.id,
        "course_name": klass.course_name,
        "my_role": my_role,
        "assignment_count": Worksheet.query.filter_by(class_id=klass.id).count(),
        "section_count": Section.query.filter_by(class_id=klass.id).count(),
        "student_count": active_participants,
        "is_archived": klass.is_archived,
        "join_code": klass.join_code,
    }


def _serialize_section(section, user):
    co_teachers = SectionCoTeacher.query.filter_by(section_id=section.id).all()
    return {
        "id": section.id,
        "class_id": section.class_id,
        "course_name": section.klass.course_name,
        "name": section.name,
        "assigned_numbers": section.assigned_numbers or "",
        "ta_id": section.ta_user_id,
        "ta_name": section.ta.display_name if section.ta else None,
        "ta_email": section.ta.email if section.ta else None,
        "co_teachers": [
            {"id": c.user.id, "display_name": c.user.display_name, "email": c.user.email} for c in co_teachers
        ],
    }


def _serialize_worksheet(worksheet):
    return {
        "id": worksheet.id,
        "class_id": worksheet.class_id,
        "slug": worksheet.slug,
        "title": worksheet.title,
        "description": worksheet.description,
        "is_published": worksheet.is_published,
        "share_code": worksheet.share_code,
    }
