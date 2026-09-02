"""The student entry point: a per-assignment share link.

A TA publishes a worksheet, gets `/w/<share_code>`, and hands it out.
A student (no account, no class enrollment) opens it, types a display
name and a group number, and starts working. Identity is a signed-cookie
participant key (server/participant.py); the group + membership rows are
transient and swept by the retention job.
"""

from flask import Blueprint, jsonify, request

from server.auth import get_current_user
from server.extensions import db
from server.models.group import Group, GroupMembership
from server.models.worksheet import Worksheet
from server.participant import (
    current_participant_key,
    ensure_participant_for_staff,
    get_participant,
    mint_participant,
    participant_required,
)
from server.utils import utcnow

w_bp = Blueprint("w", __name__)


def _resolve(share_code):
    return Worksheet.query.filter_by(share_code=share_code, is_published=True).first()


def _my_live_group_id(class_id):
    """If the caller already has a participant cookie and a membership in a
    group of this class, return that group id so the UI can offer 'resume'."""
    key = current_participant_key()
    if not key:
        return None
    row = (
        GroupMembership.query.join(Group, Group.id == GroupMembership.group_id)
        .filter(GroupMembership.participant_key == key, Group.class_id == class_id)
        .order_by(GroupMembership.joined_at.desc())
        .first()
    )
    return row.group_id if row else None


def _identity(name):
    """The participant key to act as. A logged-in staff member keeps a
    stable staff-scoped key (so "view as student" is consistent); everyone
    else mints or renames an anonymous one."""
    user = get_current_user()
    if user is not None:
        return ensure_participant_for_staff(user)
    return mint_participant(name, key=current_participant_key())


def _display_name(fallback):
    return (get_participant() or {}).get("name") or fallback


@w_bp.get("/<share_code>")
def resolve_share_code(share_code):
    worksheet = _resolve(share_code)
    if worksheet is None:
        return jsonify(error="that link is not valid — check with your TA"), 404
    return jsonify(
        worksheet_id=worksheet.id,
        worksheet_title=worksheet.title,
        class_id=worksheet.class_id,
        class_name=worksheet.klass.course_name,
        resumable_group_id=_my_live_group_id(worksheet.class_id),
        my_name=(get_participant() or {}).get("name") or "",
    )


@w_bp.post("/<share_code>/join")
def join_by_number(share_code):
    worksheet = _resolve(share_code)
    if worksheet is None:
        return jsonify(error="that link is not valid — check with your TA"), 404

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name and get_current_user() is None:
        return jsonify(error="enter your name so your group knows who you are"), 400
    try:
        number = int(data.get("number"))
    except (TypeError, ValueError):
        return jsonify(error="a group number is required"), 400
    if number < 1 or number > 999:
        return jsonify(error="group number must be between 1 and 999"), 400

    key = _identity(name)
    display = _display_name(name)

    group = Group.query.filter_by(class_id=worksheet.class_id, number=number, is_individual=False).first()
    if group is None:
        group = Group(class_id=worksheet.class_id, number=number, name=f"Group {number}", is_individual=False)
        db.session.add(group)
        db.session.flush()

    membership = GroupMembership.query.filter_by(group_id=group.id, participant_key=key).first()
    if membership is None:
        db.session.add(GroupMembership(group_id=group.id, participant_key=key, participant_name=display))
    else:
        membership.participant_name = display
    group.last_activity_at = utcnow()
    db.session.commit()
    return jsonify(group_id=group.id, worksheet_id=worksheet.id, class_id=worksheet.class_id)


@w_bp.post("/<share_code>/work-individually")
def work_individually(share_code):
    worksheet = _resolve(share_code)
    if worksheet is None:
        return jsonify(error="that link is not valid — check with your TA"), 404

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name and get_current_user() is None:
        return jsonify(error="enter your name first"), 400

    key = _identity(name)
    display = _display_name(name)

    group = (
        Group.query.filter_by(class_id=worksheet.class_id, is_individual=True)
        .join(GroupMembership, GroupMembership.group_id == Group.id)
        .filter(GroupMembership.participant_key == key)
        .first()
    )
    if group is None:
        group = Group(
            class_id=worksheet.class_id,
            name=f"{display} (individual)",
            is_individual=True,
            last_activity_at=utcnow(),
        )
        db.session.add(group)
        db.session.flush()
        db.session.add(GroupMembership(group_id=group.id, participant_key=key, participant_name=display))
    db.session.commit()
    return jsonify(group_id=group.id, worksheet_id=worksheet.id, class_id=worksheet.class_id)


@w_bp.get("/<share_code>/g/<int:group_id>/export")
@participant_required
def export_work(share_code, group_id):
    from server.services.export_html import render_export

    worksheet = _resolve(share_code)
    if worksheet is None:
        return jsonify(error="that link is not valid"), 404
    group = Group.query.get(group_id)
    if group is None or group.class_id != worksheet.class_id:
        return jsonify(error="group not found"), 404
    key = current_participant_key()
    if GroupMembership.query.filter_by(group_id=group_id, participant_key=key).first() is None:
        return jsonify(error="not a member of this group"), 403
    return render_export(worksheet, group, key)
