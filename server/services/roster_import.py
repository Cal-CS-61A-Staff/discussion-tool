"""Imports course rosters. Two shapes, from two different real sheets:

`import_ta_roster` — the staff-assignment sheet (TA name, then up to N
repeating (Section, Groups) column pairs). TAs have no email in this sheet,
so matching is by (case-insensitive, trimmed) display_name.

`import_enrollment_roster` — the fuller per-student enrollment export (one
row per student per section-meeting: Student Email, Staff Email, Location,
Day, Start, Type). This one has real emails for both students and staff, so
matching is by email instead — the more robust, forward-compatible identity
key once real Google/Canvas OAuth replaces the login stub (see
server/blueprints/auth.py:login, which already prefers an email match over
creating a new user when a login provides one).

Both are uploaded as a CSV file from the Admin page (comma-separated, e.g.
Google Sheets' File → Download → Comma Separated Values export) — the
delimiter is auto-detected (see _detect_delimiter) so a legacy
tab-separated paste still works too. Both are idempotent — re-importing an
updated sheet reuses what already matches rather than duplicating it.

Neither turns "which groups" data into actual Group rows: the staff sheet's
"Groups" columns (e.g. "188-193") number groups on a scheme spanning the
whole course, which doesn't correspond to this app's per-section-local
Group.number (1, 2, 3... within each section); assigning actual groups
stays the existing manual step (the "+ Add groups" page). The enrollment
sheet only ever says which *section* a student belongs to
(SectionEnrollment) — not which group within it.
"""

import csv
import io

from sqlalchemy import func

from server.extensions import db
from server.models.klass import Class
from server.models.section import Section, SectionEnrollment
from server.models.user import User

DEFAULT_COURSE_NAME = "CS 61A"


def _detect_delimiter(text):
    """Both imports used to only ever see text pasted straight out of
    Google Sheets (tab-separated). Now that the Admin page uploads an
    actual .csv file instead, the real-world delimiter is comma — but
    detect rather than hard-code it so a tab-separated paste still works
    too (anyone scripting against this endpoint directly, e.g.), rather
    than silently mis-parsing into one giant first column.
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


def parse_ta_roster(text):
    """Returns [{"name": str, "sections": [str, ...]}, ...] — one entry per
    non-blank row, `sections` holding only the non-empty, non-"N/A" Section
    cells (the "Groups" cell of each pair is read but discarded, and the
    header row is skipped by assuming row 0 is always the header).
    """
    rows = list(csv.reader(io.StringIO(text), delimiter=_detect_delimiter(text)))
    if not rows:
        return []

    entries = []
    for row in rows[1:]:
        if not row or not row[0].strip():
            continue
        name = row[0].strip()
        sections = []
        for i in range(1, len(row), 2):
            label = row[i].strip()
            if label and label.upper() != "N/A":
                sections.append(label)
        entries.append({"name": name, "sections": sections})
    return entries


def find_ta_by_name(name):
    return User.query.filter(User.role == "ta", func.lower(User.display_name) == name.strip().lower()).first()


def import_ta_roster(text, course_name=DEFAULT_COURSE_NAME):
    """Find-or-creates a TA User per row and a Section per section label,
    then assigns Section.ta_user_id — idempotent, so re-importing an updated
    sheet is safe (existing TAs/sections are matched and reused, not
    duplicated).
    """
    entries = parse_ta_roster(text)
    summary = {"tas_created": 0, "tas_matched": 0, "sections_created": 0, "sections_assigned": 0}
    klass = _find_or_create_class(course_name)

    for entry in entries:
        ta = find_ta_by_name(entry["name"])
        if ta is None:
            ta = User(display_name=entry["name"], role="ta")
            db.session.add(ta)
            db.session.flush()
            summary["tas_created"] += 1
        else:
            summary["tas_matched"] += 1

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


def find_user_by_email(email):
    return User.query.filter(func.lower(User.email) == email.strip().lower()).first()


def _placeholder_display_name(email):
    return email.split("@")[0]


def enrollment_section_label(day, start, location):
    return f"{day} {start} ({location})"


def parse_enrollment_roster(text, discussion_type="Discussion"):
    """Parses the real per-student enrollment export: one row per (student,
    section-meeting), columns `Student Email`, `Staff Email`, `Location`,
    `Day`, `Start`, `Type` (tab-separated, e.g. pasted from Google Sheets).
    The same sheet also lists Lab/Office-Hours/Lecture rows for other
    meeting types — only rows where Type == discussion_type are kept, since
    this app is discussion-only.

    Returns [{"student_email", "staff_email", "day", "start", "location"}].
    A row missing its email/day/start/location is skipped rather than
    raising — a roster export is exactly the kind of input worth tolerating
    a few incomplete rows in, rather than failing the whole import.
    """
    reader = csv.DictReader(io.StringIO(text), delimiter=_detect_delimiter(text))
    rows = []
    for row in reader:
        if (row.get("Type") or "").strip().lower() != discussion_type.lower():
            continue
        student_email = (row.get("Student Email") or "").strip()
        day = (row.get("Day") or "").strip()
        start = (row.get("Start") or "").strip()
        location = (row.get("Location") or "").strip()
        if not (student_email and day and start and location):
            continue
        rows.append(
            {
                "student_email": student_email,
                "staff_email": (row.get("Staff Email") or "").strip(),
                "day": day,
                "start": start,
                "location": location,
            }
        )
    return rows


def import_enrollment_roster(text, course_name=DEFAULT_COURSE_NAME):
    """Find-or-creates a Section per unique (day, start, location), assigns
    its TA from that group's Staff Email, and records every Student Email as
    enrolled in it (server/models/section.py:SectionEnrollment). A
    roster-created TA/student has no real name yet — just a placeholder
    derived from their email — until they actually log in with a display
    name, at which point server/blueprints/auth.py:login fills it in on
    that same (email-matched) account rather than creating a new one.

    Idempotent: re-importing an updated sheet reuses existing sections,
    users, and enrollments rather than duplicating them, and re-resolves
    each section's TA from whatever the sheet says now.
    """
    rows = parse_enrollment_roster(text)
    summary = {
        "sections_created": 0,
        "sections_matched": 0,
        "tas_created": 0,
        "tas_matched": 0,
        "enrollments_created": 0,
        "enrollments_matched": 0,
    }
    klass = _find_or_create_class(course_name)
    resolved_sections = {}

    for row in rows:
        key = (row["day"], row["start"], row["location"])
        section = resolved_sections.get(key)
        if section is None:
            label = enrollment_section_label(*key)
            section = Section.query.filter_by(class_id=klass.id, name=label).first()
            if section is None:
                section = Section(class_id=klass.id, name=label)
                db.session.add(section)
                db.session.flush()
                summary["sections_created"] += 1
            else:
                summary["sections_matched"] += 1

            if row["staff_email"]:
                ta = find_user_by_email(row["staff_email"])
                if ta is None:
                    ta = User(display_name=_placeholder_display_name(row["staff_email"]), role="ta", email=row["staff_email"].lower())
                    db.session.add(ta)
                    db.session.flush()
                    summary["tas_created"] += 1
                else:
                    summary["tas_matched"] += 1
                section.ta_user_id = ta.id

            resolved_sections[key] = section

        email = row["student_email"].lower()
        enrollment = SectionEnrollment.query.filter_by(section_id=section.id, student_email=email).first()
        if enrollment is None:
            db.session.add(SectionEnrollment(section_id=section.id, student_email=email))
            summary["enrollments_created"] += 1
        else:
            summary["enrollments_matched"] += 1

    db.session.commit()
    return summary
