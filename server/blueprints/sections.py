from flask import Blueprint, jsonify, request
from sqlalchemy import func

from server.auth import get_current_user, login_required, role_required
from server.config import Config
from server.extensions import db
from server.models.group import Group, GroupMembership
from server.models.section import Section
from server.models.worksheet import Worksheet

sections_bp = Blueprint("sections", __name__)


@sections_bp.get("/sections")
@login_required
def list_sections():
    user = get_current_user()
    sections = Section.query.all()
    return jsonify(sections=[_serialize_section(s, user) for s in sections])


@sections_bp.get("/sections/<int:section_id>/worksheets")
@login_required
def section_worksheets(section_id):
    """Students only ever see published assignments — drafts a TA is still
    building stay invisible until explicitly released (see
    Worksheet.is_published). TAs see everything, draft or not.
    """
    Section.query.get_or_404(section_id)
    user = get_current_user()
    query = Worksheet.query.filter_by(section_id=section_id)
    if user.role != "ta":
        query = query.filter_by(is_published=True)
    # Due date first; assignments with no due date yet fall back to
    # creation order rather than being sorted arbitrarily.
    worksheets = query.order_by(func.coalesce(Worksheet.due_date, Worksheet.created_at)).all()
    return jsonify(worksheets=[_serialize_worksheet(w) for w in worksheets])


@sections_bp.get("/me/groups")
@login_required
def my_groups():
    user = get_current_user()
    memberships = GroupMembership.query.filter_by(user_id=user.id).all()
    return jsonify(groups=[_serialize_group_summary(m.group) for m in memberships])


@sections_bp.get("/sections/<int:section_id>/groups")
@role_required("ta")
def section_groups(section_id):
    """TA-only — students never see the roster of who's in which group,
    only their own (via /me/groups) or the one they successfully join by
    number below.
    """
    section = Section.query.get_or_404(section_id)
    groups = Group.query.filter_by(section_id=section.id, is_individual=False).order_by(Group.number).all()
    return jsonify(groups=[_serialize_group_summary(g) for g in groups])


@sections_bp.post("/sections/<int:section_id>/groups/join")
@login_required
def join_group_by_number(section_id):
    """Student types their TA-assigned group number to join it — no
    visible group list, no join code. Idempotent if already a member.
    """
    user = get_current_user()
    if user.role != "student":
        return jsonify(error="only students join groups"), 403

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
    """
    user = get_current_user()
    if user.role != "student":
        return jsonify(error="only students can work individually"), 403

    Section.query.get_or_404(section_id)

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


def _serialize_section(section, user):
    """worksheet_count reflects what `user` can actually see — a student
    shouldn't count assignments that haven't been released yet, but a TA
    (who can see and needs to manage drafts) sees the true total.
    """
    query = Worksheet.query.filter_by(section_id=section.id)
    if user.role != "ta":
        query = query.filter_by(is_published=True)
    return {
        "id": section.id,
        "course_name": section.course_name,
        "name": section.name,
        "worksheet_count": query.count(),
    }


def _serialize_worksheet(worksheet):
    return {
        "id": worksheet.id,
        "slug": worksheet.slug,
        "title": worksheet.title,
        "description": worksheet.description,
        "due_date": worksheet.due_date.isoformat() if worksheet.due_date else None,
        "is_published": worksheet.is_published,
    }


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
