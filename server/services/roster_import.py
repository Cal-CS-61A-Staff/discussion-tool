"""Staff roster import and user lookups.

`import_ta_roster` reads the staff sheet (columns `Name, Email, Sections`,
uploaded from the Admin page — comma-separated, delimiter auto-detected so
a tab-separated paste also works). Each row is matched by email (falling
back to name), granted a 'staff' ClassMembership for the course, and made
the TA of a find-or-created Room per section label. Idempotent.

There is no student roster — a student joins a class by entering its
`join_code` (server/blueprints/sections.py:join_class).
"""

import csv
import io

from sqlalchemy import func

from server.extensions import db
from server.models.klass import Class, ClassMembership
from server.models.section import Section
from server.models.user import User
from server.utils import generate_join_code

DEFAULT_COURSE_NAME = "CS 61A"


def _detect_delimiter(text):
    """Real-world input is a downloaded .csv (comma), but detect rather
    than hard-code so a tab-separated paste from Google Sheets still parses
    instead of collapsing into one giant column.
    """
    sample = text.splitlines()[0] if text.splitlines() else text
    try:
        return csv.Sniffer().sniff(sample, delimiters="\t,").delimiter
    except csv.Error:
        return ","


def _find_or_create_class(course_name):
    klass = Class.query.filter_by(course_name=course_name).first()
    if klass is None:
        code = generate_join_code()
        while Class.query.filter_by(join_code=code).first() is not None:
            code = generate_join_code()
        klass = Class(course_name=course_name, join_code=code)
        db.session.add(klass)
        db.session.flush()
    return klass


def find_user_by_email(email):
    return User.query.filter(func.lower(User.email) == email.strip().lower()).first()


def find_ta_by_name(name):
    return User.query.filter(User.role == "ta", func.lower(User.display_name) == name.strip().lower()).first()


def _placeholder_display_name(email):
    return email.split("@")[0]


def _rows(text):
    return csv.DictReader(io.StringIO(text), delimiter=_detect_delimiter(text))


def _get(row, *names):
    """Case-insensitive column fetch — tolerates `Email`/`email`/` Email `."""
    lowered = {(k or "").strip().lower(): (v or "") for k, v in row.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()].strip()
    return ""


# --------------------------------------------------------------------------
# TA roster: Name, Email, Sections
# --------------------------------------------------------------------------


def _split_sections(cell):
    parts = []
    for chunk in cell.replace("\n", ";").split(";"):
        label = chunk.strip()
        if label and label.upper() != "N/A":
            parts.append(label)
    return parts


def parse_ta_roster(text):
    """Returns [{"name", "email", "sections": [...]}] — one entry per
    non-blank row."""
    entries = []
    for row in _rows(text):
        name = _get(row, "name")
        email = _get(row, "email")
        if not name and not email:
            continue
        entries.append(
            {"name": name, "email": email, "sections": _split_sections(_get(row, "sections", "section"))}
        )
    return entries


def import_ta_roster(text, course_name=DEFAULT_COURSE_NAME):
    """Find-or-creates a staff member per row (matched by email, then
    name), grants them a 'staff' ClassMembership for the course, and
    find-or-creates a Room (Section) per section label with them as the
    room's TA. Idempotent.
    """
    entries = parse_ta_roster(text)
    summary = {"tas_created": 0, "tas_matched": 0, "sections_created": 0, "sections_assigned": 0}
    klass = _find_or_create_class(course_name)

    for entry in entries:
        ta = None
        if entry["email"]:
            ta = find_user_by_email(entry["email"])
        if ta is None and entry["name"]:
            ta = find_ta_by_name(entry["name"])

        if ta is None:
            display_name = entry["name"] or (
                _placeholder_display_name(entry["email"]) if entry["email"] else "TA"
            )
            ta = User(display_name=display_name, role="student", email=entry["email"].lower() or None)
            db.session.add(ta)
            db.session.flush()
            summary["tas_created"] += 1
        else:
            summary["tas_matched"] += 1
            if entry["email"] and not ta.email:
                ta.email = entry["email"].lower()
            if entry["name"] and ta.display_name == _placeholder_display_name(ta.email or ""):
                ta.display_name = entry["name"]

        grant_class_staff(ta, klass.id)

        for label in entry["sections"]:
            section = Section.query.filter_by(class_id=klass.id, name=label).first()
            if section is None:
                section = Section(class_id=klass.id, name=label)
                db.session.add(section)
                db.session.flush()
                summary["sections_created"] += 1
            section.ta_user_id = ta.id
            summary["sections_assigned"] += 1

    db.session.commit()
    return summary


def grant_class_staff(user, class_id):
    """Idempotently give `user` a 'staff' ClassMembership for the class
    (raising a pre-existing 'student' membership to 'staff')."""
    membership = ClassMembership.query.filter_by(user_id=user.id, class_id=class_id).first()
    if membership is None:
        db.session.add(ClassMembership(user_id=user.id, class_id=class_id, role="staff"))
    elif membership.role != "staff":
        membership.role = "staff"


def add_admin_by_email(email, name=None):
    """Find-or-create an account for a single email and grant it the
    'admin' role (the Admin page's "add an admin" input). 'role' is a
    single column and 'admin' is a strict superset of 'ta'/'student' in
    this app (see server/auth.py:role_required), so promoting a TA here
    keeps every section they owned or co-taught — they just gain the
    admin-only actions on top. A brand-new account can be seeded from just
    an email, before the person has ever signed in, exactly like
    add_ta_by_email above."""
    email = email.strip().lower()
    user = find_user_by_email(email)
    if user is None:
        user = User(
            display_name=(name or "").strip() or _placeholder_display_name(email), role="admin", email=email
        )
        db.session.add(user)
    else:
        user.role = "admin"
        if name and name.strip():
            user.display_name = name.strip()
    db.session.commit()
    return user

