from flask import Blueprint, jsonify

from server.auth import get_current_user, login_required, require_class_access
from server.extensions import db
from server.models.group import Group
from server.models.worksheet import Worksheet
from server.services import serializers
from server.services.watch_list import watched_numbers_for

ta_bp = Blueprint("ta", __name__)


@ta_bp.get("/<int:worksheet_id>/dashboard")
@login_required
def dashboard(worksheet_id):
    """Live view of the assignment, one tile per group **number** the
    caller is watching (seeded from their rooms, then editable — see
    PUT /api/classes/:id/watched-numbers). A watched number nobody has
    entered shows as an empty tile.
    """
    worksheet = Worksheet.query.get_or_404(worksheet_id)
    user = get_current_user()
    error = require_class_access(user, worksheet.klass)
    if error:
        return error

    numbers = watched_numbers_for(user, worksheet.klass)
    by_number = {}
    if numbers:
        by_number = {
            g.number: g
            for g in Group.query.filter(
                Group.class_id == worksheet.class_id,
                Group.is_individual.is_(False),
                Group.number.in_(numbers),
            ).all()
        }
    entries = [(n, by_number.get(n)) for n in numbers]
    return jsonify(groups=serializers.build_dashboard(worksheet_id, entries))
