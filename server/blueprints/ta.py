from flask import Blueprint, jsonify

from server.auth import role_required
from server.models.group import Group
from server.models.worksheet import Worksheet
from server.services import serializers

ta_bp = Blueprint("ta", __name__)


@ta_bp.get("/<int:worksheet_id>/dashboard")
@role_required("ta")
def dashboard(worksheet_id):
    """Assignment-scoped: progress is per-(group, worksheet) now (see
    GroupAssignmentProgress), so "how's the class doing" is naturally asked
    one assignment at a time.
    """
    worksheet = Worksheet.query.get_or_404(worksheet_id)
    groups = Group.query.filter_by(section_id=worksheet.section_id, is_individual=False).all()
    return jsonify(groups=serializers.build_dashboard(worksheet_id, groups))
