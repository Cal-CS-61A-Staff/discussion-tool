"""Course roster imports and lookups.

Two CSV shapes, both uploaded from the Admin page (comma-separated, e.g.
Google Sheets' File -> Download -> Comma Separated Values), delimiter
auto-detected so a tab-separated paste still works:

`import_ta_roster` — staff sheet: columns `Name, Email, Sections`, where
Sections is a single cell holding a `;`- (or newline-) separated list of
section labels the TA teaches. Matched by email (falling back to name);
each section label is find-or-created under the course and assigned to
that TA.

`import_student_roster` — course roster: columns `Email, Name` (Name
optional). Each email becomes a ClassEnrollment row for the given class;
if a name is present and no account matches that email yet, a placeholder
student User is created so their name shows before they ever log in.

Both are idempotent. Neither creates Group rows — assigning students to
groups is done by the students themselves on the join page, and adding
groups stays the manual "+ Add groups" step.
"""

import csv
import io

from sqlalchemy import func

from server.extensions import db
from server.models.klass import Class, ClassEnrollment
from server.models.section import Section
from server.models.user import User

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
        klass = Class(course_name=course_name)
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
    """Find-or-creates a TA per row (matched by email, then name) and a
    Section per section label, then assigns Section.ta_user_id. Idempotent.
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
            ta = User(display_name=display_name, role="ta", email=entry["email"].lower() or None)
            db.session.add(ta)
            db.session.flush()
            summary["tas_created"] += 1
        else:
            summary["tas_matched"] += 1
            if entry["email"] and not ta.email:
                ta.email = entry["email"].lower()
            if entry["name"] and ta.display_name == _placeholder_display_name(ta.email or ""):
                ta.display_name = entry["name"]

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


def add_ta_by_email(email, name=None):
    """Find-or-create a TA account for a single email (the Admin page's
    "add a TA" input). A plain student/None account with that email is
    promoted to 'ta'."""
    email = email.strip().lower()
    ta = find_user_by_email(email)
    if ta is None:
        ta = User(display_name=(name or "").strip() or _placeholder_display_name(email), role="ta", email=email)
        db.session.add(ta)
    else:
        ta.role = "ta"
        if name and name.strip():
            ta.display_name = name.strip()
    db.session.commit()
    return ta


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


# --------------------------------------------------------------------------
# Student roster: Email, Name
# --------------------------------------------------------------------------


def parse_student_roster(text):
    """Returns [{"email", "name"}] — one entry per row with a non-blank
    Email."""
    entries = []
    for row in _rows(text):
        email = _get(row, "email", "student email")
        if not email:
            continue
        entries.append({"email": email, "name": _get(row, "name", "student name")})
    return entries


def import_student_roster(text, class_id):
    """Records every email as enrolled in `class_id` (ClassEnrollment), and
    for any row that has a name but no matching account yet, creates a
    placeholder student User so the name is visible before first login.
    Idempotent.
    """
    entries = parse_student_roster(text)
    summary = {"enrollments_created": 0, "enrollments_matched": 0, "students_created": 0}

    for entry in entries:
        email = entry["email"].lower()
        enrollment = ClassEnrollment.query.filter_by(class_id=class_id, student_email=email).first()
        if enrollment is None:
            db.session.add(ClassEnrollment(class_id=class_id, student_email=email))
            summary["enrollments_created"] += 1
        else:
            summary["enrollments_matched"] += 1

        if entry["name"] and find_user_by_email(email) is None:
            db.session.add(User(display_name=entry["name"], role="student", email=email))
            summary["students_created"] += 1

    db.session.commit()
    return summary
