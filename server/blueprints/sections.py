from flask import Blueprint, jsonify, request
from sqlalchemy import distinct, func

from server.auth import (
    get_current_user,
    is_class_staff,
    login_required,
    require_class_access,
    require_class_membership,
    require_section_access,
)
from server.extensions import db
from server.models.group import Group, GroupMembership
from server.models.klass import Class, ClassMembership
from server.models.section import Section, SectionCoTeacher
from server.models.user import User
from server.models.worksheet import Worksheet
from server.services import serializers
from server.services.number_spec import parse_number_spec
from server.services.roster_import import _placeholder_display_name, find_user_by_email
from server.services.watch_list import set_watched_numbers, watched_numbers_for

sections_bp = Blueprint("sections", __name__)


def _my_role_in(user, class_id, staff_class_ids, member_roles):
    if user.role == "admin":
        return "staff"
    if class_id in staff_class_ids:
        return "staff"
    return member_roles.get(class_id)


@sections_bp.get("/classes")
@login_required
def list_classes():
    """A student sees only classes they've joined (by code); a staff
    member sees classes they staff; an admin sees every class. Each class
    carries `my_role` ('staff' | 'student') so the frontend can render the
    right surface.
    """
    user = get_current_user()
    member_roles = {
        m.class_id: m.role for m in ClassMembership.query.filter_by(user_id=user.id).all()
    }
    staff_class_ids = {cid for cid, role in member_roles.items() if role == "staff"}

    if user.role == "admin":
        classes = Class.query.all()
    elif member_roles:
        classes = Class.query.filter(Class.id.in_(member_roles.keys())).all()
    else:
        classes = []

    return jsonify(
        classes=[
            _serialize_class(c, _my_role_in(user, c.id, staff_class_ids, member_roles)) for c in classes
        ]
    )


@sections_bp.post("/classes/join")
@login_required
def join_class():
    """A student enters a class's join code once to gain access. Idempotent
    — re-entering a code you're already in just returns the class."""
    user = get_current_user()
    code = (request.get_json(silent=True) or {}).get("code") or ""
    code = code.strip().upper()
    if not code:
        return jsonify(error="a join code is required"), 400

    klass = Class.query.filter_by(join_code=code).first()
    if klass is None:
        return jsonify(error="no class has that join code"), 404

    membership = ClassMembership.query.filter_by(user_id=user.id, class_id=klass.id).first()
    if membership is None:
        db.session.add(ClassMembership(user_id=user.id, class_id=klass.id, role="student"))
        db.session.commit()
        membership_role = "student"
    else:
        membership_role = membership.role

    return jsonify(klass=_serialize_class(klass, "staff" if user.role == "admin" else membership_role))


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
    """Assignments in a class. A student must be a member of the class and
    only sees published ones; a staff member (or admin) sees drafts too.
    """
    klass = Class.query.get_or_404(class_id)
    user = get_current_user()
    staff = is_class_staff(user, klass)
    if not staff:
        error = require_class_membership(user, klass)
        if error:
            return error
    query = Worksheet.query.filter_by(class_id=klass.id)
    if not staff:
        query = query.filter_by(is_published=True)
    worksheets = query.order_by(Worksheet.created_at).all()
    return jsonify(worksheets=[_serialize_worksheet(w, user) for w in worksheets])


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


@sections_bp.get("/me/groups")
@login_required
def my_groups():
    user = get_current_user()
    memberships = GroupMembership.query.filter_by(user_id=user.id).all()
    return jsonify(groups=[_serialize_group_summary(m.group) for m in memberships])


@sections_bp.post("/classes/<int:class_id>/groups/join")
@login_required
def join_group_by_number(class_id):
    """Pensive-style join: any class member types a group number; everyone
    on the same number in this class is in the same group. Optionally
    names the group. Find-or-create, idempotent on re-join.
    """
    user = get_current_user()
    klass = Class.query.get_or_404(class_id)
    error = require_class_membership(user, klass)
    if error:
        return error

    data = request.get_json(silent=True) or {}
    try:
        number = int(data.get("number"))
    except (TypeError, ValueError):
        return jsonify(error="a group number is required"), 400
    if number < 1 or number > 999:
        return jsonify(error="group number must be between 1 and 999"), 400
    name = (data.get("name") or "").strip()

    group = Group.query.filter_by(class_id=class_id, number=number, is_individual=False).first()
    if group is None:
        group = Group(class_id=class_id, number=number, name=name or f"Group {number}", is_individual=False)
        db.session.add(group)
        db.session.flush()
    elif name:
        group.name = name

    if GroupMembership.query.filter_by(group_id=group.id, user_id=user.id).first() is None:
        db.session.add(GroupMembership(group_id=group.id, user_id=user.id))
    db.session.commit()

    return jsonify(group=_serialize_group_summary(group))


@sections_bp.post("/classes/<int:class_id>/work-individually")
@login_required
def work_individually(class_id):
    """Creates-or-reuses the caller's personal (is_individual) group for
    this class — the "work individually" option alongside entering a
    number. Reuses all the same group machinery for a group of one.

    Also backs "View as student" for staff: a class member (staff
    included) gets the same solo flow a student would. Excluded from grade
    rollups / dashboards so it never looks like a real attempt.
    """
    user = get_current_user()
    klass = Class.query.get_or_404(class_id)
    error = require_class_membership(user, klass)
    if error:
        return error

    group = (
        Group.query.filter_by(class_id=class_id, is_individual=True)
        .join(GroupMembership, GroupMembership.group_id == Group.id)
        .filter(GroupMembership.user_id == user.id)
        .first()
    )
    if group is None:
        group = Group(class_id=class_id, name=f"{user.display_name} (individual)", is_individual=True)
        db.session.add(group)
        db.session.flush()
        db.session.add(GroupMembership(group_id=group.id, user_id=user.id))
        db.session.commit()

    return jsonify(group=_serialize_group_summary(group))


def _serialize_membership(membership):
    return {
        "user_id": membership.user.id,
        "display_name": membership.user.display_name,
        "email": membership.user.email,
        "role": membership.role,
    }


def _serialize_class(klass, my_role):
    query = Worksheet.query.filter_by(class_id=klass.id)
    if my_role != "staff":
        query = query.filter_by(is_published=True)
    student_count = (
        db.session.query(func.count(distinct(GroupMembership.user_id)))
        .join(Group, Group.id == GroupMembership.group_id)
        .filter(Group.class_id == klass.id)
        .scalar()
    ) or 0
    payload = {
        "id": klass.id,
        "course_name": klass.course_name,
        "my_role": my_role,
        "assignment_count": query.count(),
        "section_count": Section.query.filter_by(class_id=klass.id).count(),
        "student_count": student_count,
        "is_archived": klass.is_archived,
    }
    if my_role == "staff":
        payload["join_code"] = klass.join_code
    return payload


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


def _serialize_worksheet(worksheet, user=None):
    payload = {
        "id": worksheet.id,
        "class_id": worksheet.class_id,
        "slug": worksheet.slug,
        "title": worksheet.title,
        "description": worksheet.description,
        "is_published": worksheet.is_published,
    }
    if user is not None:
        rating, group_id = serializers.student_worksheet_progress(user, worksheet)
        payload["my_rating"] = rating
        payload["my_group_id"] = group_id
    return payload


def _serialize_group_summary(group):
    members = GroupMembership.query.filter_by(group_id=group.id).all()
    return {
        "id": group.id,
        "number": group.number,
        "name": group.name,
        "class_id": group.class_id,
        "is_individual": group.is_individual,
        "member_count": len(members),
        "member_names": [m.user.display_name for m in members],
    }
