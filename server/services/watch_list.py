"""A staff member's live-dashboard watch list — which group numbers they
watch for a class. Seeded once from the rooms they run
(Section.assigned_numbers), then freely edited. See
server/models/ta_watch.py and server/blueprints/ta.py.
"""

from server.auth import runs_room
from server.extensions import db
from server.models.section import Section
from server.models.ta_watch import TaWatchedNumber
from server.services.number_spec import parse_number_spec


def _seed(user, klass):
    numbers = set()
    for section in Section.query.filter_by(class_id=klass.id).all():
        if runs_room(user, section):
            numbers.update(parse_number_spec(section.assigned_numbers))
    for number in sorted(numbers):
        db.session.add(TaWatchedNumber(user_id=user.id, class_id=klass.id, number=number))
    if numbers:
        db.session.commit()
    return sorted(numbers)


def watched_numbers_for(user, klass):
    """The caller's watched numbers for `klass`, sorted. Seeds from their
    rooms on first access; an empty result means they run no room and
    haven't added any by hand yet."""
    rows = TaWatchedNumber.query.filter_by(user_id=user.id, class_id=klass.id).all()
    if rows:
        return sorted(r.number for r in rows)
    return _seed(user, klass)


def set_watched_numbers(user, klass, numbers):
    clean = sorted({int(n) for n in numbers if 1 <= int(n) <= 999})
    TaWatchedNumber.query.filter_by(user_id=user.id, class_id=klass.id).delete()
    for number in clean:
        db.session.add(TaWatchedNumber(user_id=user.id, class_id=klass.id, number=number))
    db.session.commit()
    return clean
