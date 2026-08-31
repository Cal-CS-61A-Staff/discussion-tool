from flask import Blueprint, jsonify, request
from sqlalchemy import func

from server.auth import (
    get_current_user,
    login_required,
    require_class_access,
    require_section_access,
    role_required,
    ta_owns_class,
    ta_owns_section,
)
from server.config import Config
from server.extensions import db
from server.models.group import Group, GroupMembership
from server.models.klass import Class, ClassEnrollment
from server.models.section import Section, SectionCoTeacher
from server.models.user import User
from server.models.worksheet import Worksheet
from server.services import serializers
from server.services.roster_import import find_user_by_email

sections_bp = Blueprint("sections", __name__)


@sections_bp.get("/classes")
@login_required
def list_classes():
    """A TA only sees classes where they own/co-teach at least one section
    (or none, until assigned) — admins and students see every class
    (students pick theirs by browsing).
    """
    user = get_current_user()
    classes = Class.query.all()
    if user.role == "ta":
        classes = [c for c in classes if ta_owns_class(user, c)]
    return jsonify(classes=[_serialize_class(c, user) for c in classes])


@sections_bp.get("/sections")
@login_required
def list_sections():
    """A TA only sees sections they're the primary TA of or a co-teacher on
    (or none, until an admin assigns them one, or an existing TA/co-teacher
    grants them co-authority) — admins and students see every section
    (students pick theirs by browsing; there's no per-student ownership).
    """
    user = get_current_user()
    sections = Section.query.all()
    if user.role == "ta":
        co_taught_ids = {
            c.section_id for c in SectionCoTeacher.query.filter_by(user_id=user.id).all()
        }
        sections = [s for s in sections if s.ta_user_id == user.id or s.id in co_taught_ids]
    return jsonify(sections=[_serialize_section(s, user) for s in sections])


@sections_bp.get("/classes/<int:class_id>/students")
@role_required("ta")
def list_class_students(class_id):
    """The course roster (ClassEnrollment) for any TA/co-teacher on the
    class, or an admin — email plus the display name if an account exists."""
    klass = Class.query.get_or_404(class_id)
    error = require_class_access(get_current_user(), klass)
    if error:
        return error

    enrollments = (
        ClassEnrollment.query.filter_by(class_id=class_id).order_by(ClassEnrollment.student_email).all()
    )
    emails = [e.student_email for e in enrollments]
    names = (
        {u.email.lower(): u.display_name for u in User.query.filter(func.lower(User.email).in_(emails)).all()}
        if emails
        else {}
    )
    students = [{"email": e.student_email, "name": names.get(e.student_email)} for e in enrollments]
    return jsonify(students=students)


@sections_bp.post("/classes/<int:class_id>/students")
@role_required("ta")
def add_class_student(class_id):
    """Add one student to the course roster by email (+ optional name).
    Any TA/co-teacher on the class, or an admin."""
    klass = Class.query.get_or_404(class_id)
    error = require_class_access(get_current_user(), klass)
    if error:
        return error

    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    name = (data.get("name") or "").strip()
    if not email or "@" not in email:
        return jsonify(error="a valid email is required"), 400

    if ClassEnrollment.query.filter_by(class_id=class_id, student_email=email).first() is None:
        db.session.add(ClassEnrollment(class_id=class_id, student_email=email))
    if name and find_user_by_email(email) is None:
        db.session.add(User(display_name=name, role="student", email=email))
    db.session.commit()
    return jsonify(ok=True)


@sections_bp.delete("/classes/<int:class_id>/students")
@role_required("ta")
def remove_class_student(class_id):
    """Remove a student from the course roster — does not delete their
    account or any group work, just their roster entry."""
    klass = Class.query.get_or_404(class_id)
    error = require_class_access(get_current_user(), klass)
    if error:
        return error

    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    ClassEnrollment.query.filter_by(class_id=class_id, student_email=email).delete()
    db.session.commit()
    return jsonify(ok=True)


@sections_bp.get("/classes/<int:class_id>/worksheets")
@login_required
def class_worksheets(class_id):
    """Same visibility rule as section_worksheets below, but addressed
    directly by class id — used by the "Assignments" tab, which lists a
    class's assignments without going through any one of its sections.
    """
    klass = Class.query.get_or_404(class_id)
    user = get_current_user()
    query = Worksheet.query.filter_by(class_id=klass.id)
    if not ta_owns_class(user, klass):
        query = query.filter_by(is_published=True)
    worksheets = query.order_by(Worksheet.created_at).all()
    return jsonify(worksheets=[_serialize_worksheet(w, user) for w in worksheets])


@sections_bp.get("/sections/<int:section_id>/worksheets")
@login_required
def section_worksheets(section_id):
    """Assignments belong to this section's *class* now (shared across
    every section in it) — students only ever see published ones, drafts a
    TA is still building stay invisible until explicitly released (see
    Worksheet.is_published). Any TA who owns/co-teaches a section of this
    class (or an admin) sees everything, draft or not; a TA unrelated to
    this class is treated like a student — published only.
    """
    section = Section.query.get_or_404(section_id)
    user = get_current_user()
    query = Worksheet.query.filter_by(class_id=section.class_id)
    if not ta_owns_class(user, section.klass):
        query = query.filter_by(is_published=True)
    worksheets = query.order_by(Worksheet.created_at).all()
    return jsonify(worksheets=[_serialize_worksheet(w) for w in worksheets])


@sections_bp.get("/sections/<int:section_id>/progress")
@role_required("ta")
def section_progress(section_id):
    """This section's own TA (or an admin) only — the "Discussions" tab's
    "View class" page: each group's roster and its progress across the
    class's assignments, deliberately with no assignment content on it.
    """
    section = Section.query.get_or_404(section_id)
    error = require_section_access(get_current_user(), section)
    if error:
        return error
    return jsonify(groups=serializers.build_section_progress(section))


@sections_bp.get("/me/groups")
@login_required
def my_groups():
    user = get_current_user()
    memberships = GroupMembership.query.filter_by(user_id=user.id).all()
    return jsonify(groups=[_serialize_group_summary(m.group) for m in memberships])


@sections_bp.get("/sections/<int:section_id>/groups")
@role_required("ta")
def section_groups(section_id):
    """This section's own TA (or an admin) only — students never see the
    roster of who's in which group, only their own (via /me/groups) or the
    one they successfully join by number below.
    """
    section = Section.query.get_or_404(section_id)
    error = require_section_access(get_current_user(), section)
    if error:
        return error
    groups = Group.query.filter_by(section_id=section.id, is_individual=False).order_by(Group.number).all()
    return jsonify(groups=[_serialize_group_summary(g) for g in groups])


@sections_bp.get("/sections/<int:section_id>/groups/joinable")
@login_required
def joinable_groups(section_id):
    """The list a student picks from on the join page — every non-individual
    group in the section with how full it is. Any signed-in user, but the
    same course-roster gate as joining applies."""
    section = Section.query.get_or_404(section_id)
    user = get_current_user()
    if user.role == "student":
        error = _enrollment_blocks_join(user, section)
        if error:
            return jsonify(error=error), 403
    groups = Group.query.filter_by(section_id=section.id, is_individual=False).order_by(Group.number).all()
    payload = []
    for g in groups:
        summary = _serialize_group_summary(g)
        summary["capacity"] = Config.MAX_GROUP_SIZE
        summary["is_full"] = summary["member_count"] >= Config.MAX_GROUP_SIZE
        payload.append(summary)
    return jsonify(groups=payload)


@sections_bp.post("/sections/<int:section_id>/groups/join")
@login_required
def join_group_by_number(section_id):
    """Student picks a group on the join page and its number is sent here.
    Idempotent if already a member."""
    user = get_current_user()
    if user.role != "student":
        return jsonify(error="only students join groups"), 403

    section = Section.query.get_or_404(section_id)
    error = _enrollment_blocks_join(user, section)
    if error:
        return jsonify(error=error), 403

    data = request.get_json(silent=True) or {}
    try:
        number = int(data.get("number"))
    except (TypeError, ValueError):
        return jsonify(error="a group number is required"), 400

    group = Group.query.filter_by(section_id=section_id, number=number, is_individual=False).first()
    if group is None:
        return jsonify(error=f"no group #{number} in this class"), 404

    member_count = GroupMembership.query.filter_by(group_id=group.id).count()
    already_in = GroupMembership.query.filter_by(group_id=group.id, user_id=user.id).first()
    if member_count >= Config.MAX_GROUP_SIZE and already_in is None:
        return jsonify(error="group is full"), 409

    if already_in is None:
        db.session.add(GroupMembership(group_id=group.id, user_id=user.id))
        db.session.commit()

    return jsonify(group=_serialize_group_summary(group))


@sections_bp.post("/sections/<int:section_id>/work-individually")
@login_required
def work_individually(section_id):
    """Creates-or-reuses the caller's personal (is_individual) group for
    this class — the "work individually" option available alongside
    joining a group on every assignment. Reuses all the same group
    machinery for a group of one rather than a parallel solo code path.

    Also backs "View as student" on the Assignments page: a TA/admin with
    access to this section gets the exact same solo group/live worksheet
    flow a student would, to sanity-check an assignment (doctests,
    prediction quiz, wording) end to end before publishing it. Their
    resulting group is excluded from grade rollups and the TA dashboard
    (see worksheet_grades) so it never gets mistaken for a real student's
    attempt.
    """
    user = get_current_user()
    section = Section.query.get_or_404(section_id)
    if user.role == "student":
        error = _enrollment_blocks_join(user, section)
        if error:
            return jsonify(error=error), 403
    elif not ta_owns_section(user, section):
        return jsonify(error="you don't have access to this class"), 403

    group = (
        Group.query.filter_by(section_id=section_id, is_individual=True)
        .join(GroupMembership, GroupMembership.group_id == Group.id)
        .filter(GroupMembership.user_id == user.id)
        .first()
    )
    if group is None:
        group = Group(section_id=section_id, name=f"{user.display_name} (individual)", is_individual=True)
        db.session.add(group)
        db.session.flush()
        db.session.add(GroupMembership(group_id=group.id, user_id=user.id))
        db.session.commit()

    return jsonify(group=_serialize_group_summary(group))


def _enrollment_blocks_join(user, section):
    """None if `user` may join a group under `section` (course-level gate),
    else an error message to surface as a banner. Only enforced when both
    (a) the user gave an email at login (server/blueprints/auth.py) and
    (b) this section's CLASS has a roster (ClassEnrollment) — a class with
    no roster stays open to anyone, and a user with no email is never gated.
    """
    if not user.email:
        return None
    class_id = section.class_id
    if not db.session.query(ClassEnrollment.id).filter_by(class_id=class_id).first():
        return None
    is_enrolled = (
        ClassEnrollment.query.filter_by(class_id=class_id, student_email=user.email.strip().lower()).first()
        is not None
    )
    if is_enrolled:
        return None
    return "you're not on the roster for this class — ask your TA to add you"


def _serialize_class(klass, user):
    """assignment_count/section_count mirror _serialize_section's
    worksheet_count logic: a student (or an unrelated TA) only counts
    released assignments, while a TA/co-teacher of any section here (or an
    admin) sees the true total, since they're trusted to manage drafts.
    """
    query = Worksheet.query.filter_by(class_id=klass.id)
    if not ta_owns_class(user, klass):
        query = query.filter_by(is_published=True)
    # Counts real participation (anyone who's joined a group under any
    # section of this class), not imported-roster enrollment — that's
    # opt-in per section and often absent entirely for a demo/open class.
    student_count = (
        db.session.query(func.count(func.distinct(GroupMembership.user_id)))
        .join(Group, Group.id == GroupMembership.group_id)
        .join(Section, Section.id == Group.section_id)
        .filter(Section.class_id == klass.id)
        .scalar()
    ) or 0
    return {
        "id": klass.id,
        "course_name": klass.course_name,
        "assignment_count": query.count(),
        "section_count": Section.query.filter_by(class_id=klass.id).count(),
        "student_count": student_count,
        "is_archived": klass.is_archived,
    }


def _serialize_section(section, user):
    """worksheet_count reflects what `user` can actually see — a student
    (or a TA unrelated to this section's class) shouldn't count assignments
    that haven't been released yet, but a TA/co-teacher of this class (or
    an admin), who can see and needs to manage drafts, sees the true total.
    Assignments belong to the class now, not the section directly (see
    server/models/klass.py) — course_name is likewise the class's.
    """
    query = Worksheet.query.filter_by(class_id=section.class_id)
    if not ta_owns_class(user, section.klass):
        query = query.filter_by(is_published=True)
    co_teachers = SectionCoTeacher.query.filter_by(section_id=section.id).all()
    return {
        "id": section.id,
        "class_id": section.class_id,
        "course_name": section.klass.course_name,
        "name": section.name,
        "worksheet_count": query.count(),
        "ta_id": section.ta_user_id,
        "ta_name": section.ta.display_name if section.ta else None,
        "ta_email": section.ta.email if section.ta else None,
        "co_teachers": [
            {"id": c.user.id, "display_name": c.user.display_name, "email": c.user.email} for c in co_teachers
        ],
    }


def _serialize_worksheet(worksheet, user=None):
    """`user` is only passed by class_worksheets (the shared Assignments
    page) — section_worksheets doesn't need a viewer's own rating, so it
    keeps calling this without one and my_rating/my_group_id stay absent.
    """
    payload = {
        "id": worksheet.id,
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
        "section_id": group.section_id,
        "is_individual": group.is_individual,
        "member_count": len(members),
        "member_names": [m.user.display_name for m in members],
    }
