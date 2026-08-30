from flask import Blueprint, jsonify

from server.auth import get_current_user, require_class_access, role_required, ta_owns_section
from server.models.group import Group
from server.models.worksheet import Worksheet
from server.services import serializers

ta_bp = Blueprint("ta", __name__)


@ta_bp.get("/<int:worksheet_id>/dashboard")
@role_required("ta")
def dashboard(worksheet_id):
    """Assignment-scoped: progress is per-(group, worksheet) now (see
    GroupAssignmentProgress), so "how's the class doing" is naturally asked
    one assignment at a time. This assignment is shared across every
    section of its class (see server/models/klass.py), but a plain TA only
    sees groups in the sections they themselves own/co-teach — sharing
    assignment content across a class's staff doesn't mean sharing every
    other section's live student activity; an admin sees all of them.
    """
    worksheet = Worksheet.query.get_or_404(worksheet_id)
    user = get_current_user()
    error = require_class_access(user, worksheet.klass)
    if error:
        return error

    sections = worksheet.klass.sections.all()
    if user.role != "admin":
        sections = [s for s in sections if ta_owns_section(user, s)]
    section_ids = [s.id for s in sections]

    groups = Group.query.filter(Group.section_id.in_(section_ids), Group.is_individual.is_(False)).all()
    return jsonify(groups=serializers.build_dashboard(worksheet_id, groups))
