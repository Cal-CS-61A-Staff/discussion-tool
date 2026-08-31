import json

from flask import Blueprint, jsonify, request
from sqlalchemy import func

from server.auth import (
    admin_required,
    get_current_user,
    login_required,
    require_class_access,
    require_section_access,
    role_required,
)
from server.blueprints.sections import _serialize_class, _serialize_section
from server.extensions import db
from server.models.attempt import Attempt
from server.models.group import Group, GroupAssignmentProgress, GroupMembership, GroupQuestionState
from server.models.klass import Class
from server.models.rating import Rating
from server.models.section import Section, SectionCoTeacher, SectionEnrollment
from server.models.test_run import TestRun
from server.models.user import User
from server.models.worksheet import Question, Worksheet
from server.services import advance as advance_service
from server.services import grading as grading_service
from server.services.roster_import import find_user_by_email, import_enrollment_roster, import_ta_roster
from server.services.test_case_grading import generate_simple_test_code

admin_bp = Blueprint("admin", __name__)

MAX_GROUPS_PER_CREATE_CALL = 50


@admin_bp.get("/tas")
@admin_required
def list_tas():
    """Admin-only — populates the "assign a TA to this section" control."""
    tas = User.query.filter_by(role="ta").order_by(User.display_name).all()
    return jsonify(tas=[{"id": t.id, "display_name": t.display_name, "email": t.email} for t in tas])


@admin_bp.put("/sections/<int:section_id>/ta")
@admin_required
def assign_section_ta(section_id):
    """Admin-only — a plain TA can't reassign their own (or anyone else's)
    section; that would let a TA grant themselves access to another
    section's groups.
    """
    section = Section.query.get_or_404(section_id)
    data = request.get_json(silent=True) or {}
    ta_user_id = data.get("ta_user_id")

    if ta_user_id is None:
        section.ta_user_id = None
    else:
        ta = User.query.get(ta_user_id)
        if ta is None or ta.role != "ta":
            return jsonify(error="ta_user_id must be an existing user with the 'ta' role"), 400
        section.ta_user_id = ta.id

    db.session.commit()
    return jsonify(section=_serialize_section(section, get_current_user()))


@admin_bp.post("/classes")
@login_required
def create_class():
    """Admin-only — deliberately not role_required("ta"): a plain TA (or
    student) gets this exact message rather than the shared decorator's
    generic "admin role required", since it's the one place a TA might
    reasonably expect staff-level access and not get it. Everything a TA
    actually *works in* day to day (creating/editing assignments, managing
    groups) stays TA-or-admin — this is scoped narrowly to standing up a
    brand new course, alongside role assignment and archiving.
    """
    user = get_current_user()
    if user.role != "admin":
        return jsonify(error="You do not have permission to create a new class."), 403

    data = request.get_json(silent=True) or {}
    course_name = (data.get("course_name") or "").strip()
    if not course_name:
        return jsonify(error="course_name is required"), 400

    klass = Class(course_name=course_name)
    db.session.add(klass)
    db.session.commit()
    return jsonify(klass=_serialize_class(klass, user)), 201


@admin_bp.put("/classes/<int:class_id>/archive")
@admin_required
def archive_class(class_id):
    """Admin-only, like create_class above — archiving and role
    assignment are the two things this app reserves for admins specifically
    beyond regular staff access, so this doesn't use require_class_access's
    ownership check at all (an admin can always act on any class).
    """
    klass = Class.query.get_or_404(class_id)
    data = request.get_json(silent=True) or {}
    is_archived = data.get("is_archived")
    if not isinstance(is_archived, bool):
        return jsonify(error="is_archived must be a boolean"), 400

    klass.is_archived = is_archived
    db.session.commit()
    return jsonify(klass=_serialize_class(klass, get_current_user()))


@admin_bp.delete("/classes/<int:class_id>")
@admin_required
def delete_class(class_id):
    """Admin-only — wipes the entire course: every section under it (with
    its groups/roster/co-teachers, same cascade as delete_section below)
    and every assignment (with its questions and grading history) —
    everything a class has, since nothing outlives its own class.
    """
    klass = Class.query.get_or_404(class_id)

    section_ids = [s.id for s in Section.query.filter_by(class_id=klass.id).with_entities(Section.id).all()]
    if section_ids:
        _delete_groups_cascade(section_ids)
        SectionEnrollment.query.filter(SectionEnrollment.section_id.in_(section_ids)).delete(
            synchronize_session=False
        )
        SectionCoTeacher.query.filter(SectionCoTeacher.section_id.in_(section_ids)).delete(synchronize_session=False)
        Section.query.filter(Section.id.in_(section_ids)).delete(synchronize_session=False)

    worksheet_ids = [w.id for w in Worksheet.query.filter_by(class_id=klass.id).with_entities(Worksheet.id).all()]
    _delete_worksheets_cascade(worksheet_ids)

    db.session.delete(klass)
    db.session.commit()
    return jsonify(ok=True)


@admin_bp.post("/sections")
@admin_required
def create_section():
    """Admin-only — a new section under an existing class, with no TA
    assigned (see assign_section_ta above) and no groups (see create_groups
    below).
    """
    data = request.get_json(silent=True) or {}
    class_id = data.get("class_id")
    name = (data.get("name") or "").strip()
    if not class_id or not name:
        return jsonify(error="class_id and name are required"), 400
    klass = Class.query.get(class_id)
    if klass is None:
        return jsonify(error="class not found"), 404

    section = Section(class_id=klass.id, name=name)
    db.session.add(section)
    db.session.commit()
    return jsonify(section=_serialize_section(section, get_current_user())), 201


def _delete_groups_cascade(section_ids):
    """Shared by delete_section and delete_class — wipes every group (and
    its progress/history) across the given sections. SQLite FK enforcement
    is off by default in this app, so cascading is done explicitly.
    """
    group_ids = [g.id for g in Group.query.filter(Group.section_id.in_(section_ids)).with_entities(Group.id).all()]
    if not group_ids:
        return
    TestRun.query.filter(TestRun.group_id.in_(group_ids)).delete(synchronize_session=False)
    Attempt.query.filter(Attempt.group_id.in_(group_ids)).delete(synchronize_session=False)
    Rating.query.filter(Rating.group_id.in_(group_ids)).delete(synchronize_session=False)
    GroupQuestionState.query.filter(GroupQuestionState.group_id.in_(group_ids)).delete(synchronize_session=False)
    GroupAssignmentProgress.query.filter(GroupAssignmentProgress.group_id.in_(group_ids)).delete(
        synchronize_session=False
    )
    GroupMembership.query.filter(GroupMembership.group_id.in_(group_ids)).delete(synchronize_session=False)
    Group.query.filter(Group.section_id.in_(section_ids)).delete(synchronize_session=False)


def _delete_worksheets_cascade(worksheet_ids):
    """Shared by delete_worksheet and delete_class — wipes every question
    (and its grading history) across the given worksheets, then the
    worksheets themselves.
    """
    if not worksheet_ids:
        return
    question_ids = [
        q.id
        for q in Question.query.filter(Question.worksheet_id.in_(worksheet_ids)).with_entities(Question.id).all()
    ]
    if question_ids:
        TestRun.query.filter(TestRun.question_id.in_(question_ids)).delete(synchronize_session=False)
        Attempt.query.filter(Attempt.question_id.in_(question_ids)).delete(synchronize_session=False)
        Rating.query.filter(Rating.question_id.in_(question_ids)).delete(synchronize_session=False)
        GroupQuestionState.query.filter(GroupQuestionState.question_id.in_(question_ids)).delete(
            synchronize_session=False
        )
    Question.query.filter(Question.worksheet_id.in_(worksheet_ids)).delete(synchronize_session=False)
    GroupAssignmentProgress.query.filter(GroupAssignmentProgress.worksheet_id.in_(worksheet_ids)).delete(
        synchronize_session=False
    )
    Worksheet.query.filter(Worksheet.id.in_(worksheet_ids)).delete(synchronize_session=False)


@admin_bp.delete("/sections/<int:section_id>")
@admin_required
def delete_section(section_id):
    """Admin-only — wipes this section's groups/progress/history and its
    enrollment/co-teacher records. Assignments aren't touched: they belong
    to the class now (server/models/klass.py), not this section, so
    deleting a section never removes any assignment content — only
    deleting the whole class does (see delete_class above).
    """
    section = Section.query.get_or_404(section_id)

    _delete_groups_cascade([section.id])
    SectionEnrollment.query.filter_by(section_id=section.id).delete(synchronize_session=False)
    SectionCoTeacher.query.filter_by(section_id=section.id).delete(synchronize_session=False)

    db.session.delete(section)
    db.session.commit()
    return jsonify(ok=True)


@admin_bp.put("/sections/<int:section_id>/details")
@role_required("ta")
def update_section_details(section_id):
    """A section's own TA/co-teacher (or an admin) can rename it — unlike
    assign_section_ta (who's in charge), this is just the section's own
    label, so it doesn't need admin_required. The class it belongs to
    (course_name) isn't editable here — see create_class/PUT /classes/:id.
    """
    section = Section.query.get_or_404(section_id)
    error = require_section_access(get_current_user(), section)
    if error:
        return error

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name is required"), 400

    section.name = name
    db.session.commit()
    return jsonify(section=_serialize_section(section, get_current_user()))


@admin_bp.get("/sections/<int:section_id>/co-teachers")
@role_required("ta")
def list_co_teachers(section_id):
    section = Section.query.get_or_404(section_id)
    error = require_section_access(get_current_user(), section)
    if error:
        return error
    co_teachers = SectionCoTeacher.query.filter_by(section_id=section.id).all()
    return jsonify(co_teachers=[_serialize_co_teacher(c) for c in co_teachers])


@admin_bp.post("/sections/<int:section_id>/co-teachers")
@role_required("ta")
def add_co_teacher(section_id):
    """Granted by anyone who already has authority over the section — the
    primary TA, an existing co-teacher, or an admin — by the co-teacher's
    email (server/services/roster_import.py:find_user_by_email), the same
    identity key roster imports and login use. That TA needs to have
    signed in at least once already (so their account exists) before they
    can be added.
    """
    section = Section.query.get_or_404(section_id)
    error = require_section_access(get_current_user(), section)
    if error:
        return error

    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    if not email:
        return jsonify(error="email is required"), 400

    ta = find_user_by_email(email)
    if ta is None or ta.role != "ta":
        return jsonify(error="no TA account found with that email — they need to sign in once first"), 404
    if ta.id == section.ta_user_id:
        return jsonify(error="that TA already owns this section"), 400

    existing = SectionCoTeacher.query.filter_by(section_id=section.id, user_id=ta.id).first()
    if existing is None:
        db.session.add(SectionCoTeacher(section_id=section.id, user_id=ta.id))
        db.session.commit()

    co_teachers = SectionCoTeacher.query.filter_by(section_id=section.id).all()
    return jsonify(co_teachers=[_serialize_co_teacher(c) for c in co_teachers]), 201


@admin_bp.delete("/sections/<int:section_id>/co-teachers/<int:user_id>")
@role_required("ta")
def remove_co_teacher(section_id, user_id):
    section = Section.query.get_or_404(section_id)
    error = require_section_access(get_current_user(), section)
    if error:
        return error

    SectionCoTeacher.query.filter_by(section_id=section.id, user_id=user_id).delete()
    db.session.commit()
    return jsonify(ok=True)


def _serialize_co_teacher(co_teacher):
    return {"id": co_teacher.user.id, "display_name": co_teacher.user.display_name, "email": co_teacher.user.email}


@admin_bp.post("/roster/import")
@admin_required
def import_roster():
    """Admin-only — pastes/uploads the staff-assignment sheet (TA name, then
    repeating (Section, Groups) column pairs; tab-separated, e.g. pasted
    straight from Google Sheets) and upserts TAs + their section assignments.
    See server/services/roster_import.py for exactly what is and isn't
    imported (the "Groups" columns are read but not used).
    """
    data = request.get_json(silent=True) or {}
    text = data.get("csv") or ""
    if not text.strip():
        return jsonify(error="csv is required"), 400
    summary = import_ta_roster(text)
    return jsonify(summary=summary)


@admin_bp.post("/roster/import-enrollment")
@admin_required
def import_enrollment():
    """Admin-only — pastes/uploads the per-student enrollment export (one
    row per student per section-meeting: Student Email, Staff Email,
    Location, Day, Start, Type; tab-separated). Only Type == "Discussion"
    rows are used. See server/services/roster_import.py for exactly what's
    imported: sections + their TA (by email) + each student's enrollment
    (which section, not which group).
    """
    data = request.get_json(silent=True) or {}
    text = data.get("csv") or ""
    if not text.strip():
        return jsonify(error="csv is required"), 400
    summary = import_enrollment_roster(text)
    return jsonify(summary=summary)


@admin_bp.post("/sections/<int:section_id>/groups")
@role_required("ta")
def create_groups(section_id):
    section = Section.query.get_or_404(section_id)
    error = require_section_access(get_current_user(), section)
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        count = int(data.get("count", 1))
    except (TypeError, ValueError):
        return jsonify(error="count must be an integer"), 400
    if count < 1 or count > MAX_GROUPS_PER_CREATE_CALL:
        return jsonify(error=f"count must be between 1 and {MAX_GROUPS_PER_CREATE_CALL}"), 400

    max_number = (
        db.session.query(func.max(Group.number)).filter_by(section_id=section.id, is_individual=False).scalar() or 0
    )

    created = []
    for offset in range(1, count + 1):
        number = max_number + offset
        group = Group(section_id=section.id, number=number, name=f"Group {number}")
        db.session.add(group)
        created.append(group)
    db.session.commit()

    return jsonify(groups=[_serialize_group(g) for g in created]), 201


@admin_bp.put("/groups/<int:group_id>")
@role_required("ta")
def rename_group(group_id):
    group = Group.query.get_or_404(group_id)
    error = require_section_access(get_current_user(), group.section)
    if error:
        return error
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name is required"), 400
    group.name = name
    db.session.commit()
    return jsonify(group=_serialize_group(group))


@admin_bp.delete("/groups/<int:group_id>")
@role_required("ta")
def delete_group(group_id):
    group = Group.query.get_or_404(group_id)
    error = require_section_access(get_current_user(), group.section)
    if error:
        return error
    # SQLite FK enforcement is off by default in this app, so cascading is
    # done explicitly rather than relying on ON DELETE CASCADE.
    TestRun.query.filter_by(group_id=group.id).delete()
    Attempt.query.filter_by(group_id=group.id).delete()
    Rating.query.filter_by(group_id=group.id).delete()
    GroupQuestionState.query.filter_by(group_id=group.id).delete()
    GroupAssignmentProgress.query.filter_by(group_id=group.id).delete()
    GroupMembership.query.filter_by(group_id=group.id).delete()
    db.session.delete(group)
    db.session.commit()
    return jsonify(ok=True)


@admin_bp.delete("/groups/<int:group_id>/members/<int:user_id>")
@role_required("ta")
def remove_group_member(group_id, user_id):
    """Removes one member from a group without touching the rest of its
    progress/history — the fix for a group stuck waiting on a rating from
    someone who crashed/left and isn't coming back: all_members_rated
    (server/services/advance.py) counts every current GroupMembership row
    with no timeout, so a member who'll never return blocks the group
    forever until removed. Their past Rating/TestRun/Attempt rows are left
    in place as history; harmless, since the readiness checks only compare
    counts for the *current* question. If they were the pen-holder,
    reassign_if_stale already treats a missing membership the same as a
    stale one, so the next /state poll from a remaining member hands the
    pen off automatically — no extra handling needed here.
    """
    group = Group.query.get_or_404(group_id)
    error = require_section_access(get_current_user(), group.section)
    if error:
        return error
    membership = GroupMembership.query.filter_by(group_id=group_id, user_id=user_id).first()
    if membership is None:
        return jsonify(error="that user is not a member of this group"), 404
    # all_members_rated (services/advance.py) treats a 0-member group as
    # never-ready, so removing the last member would make the group
    # permanently un-advanceable — the opposite of this endpoint's purpose.
    if GroupMembership.query.filter_by(group_id=group_id).count() <= 1:
        return jsonify(error="can't remove the last member of a group — delete the group instead"), 409
    db.session.delete(membership)
    db.session.commit()
    return jsonify(ok=True)


@admin_bp.post("/classes/<int:class_id>/worksheets")
@role_required("ta")
def create_worksheet(class_id):
    """Any TA who owns/co-teaches a section of this class (or an admin) can
    author an assignment — it's shared across every section in the class,
    not owned by any one of them.
    """
    klass = Class.query.get_or_404(class_id)
    error = require_class_access(get_current_user(), klass)
    if error:
        return error
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify(error="title is required"), 400

    slug_base = _slugify(title)
    slug = slug_base
    suffix = 2
    while Worksheet.query.filter_by(slug=slug).first() is not None:
        slug = f"{slug_base}-{suffix}"
        suffix += 1

    worksheet = Worksheet(
        class_id=klass.id,
        slug=slug,
        title=title,
        description=(data.get("description") or "").strip(),
    )
    db.session.add(worksheet)
    db.session.commit()

    return jsonify(worksheet=_serialize_worksheet(worksheet)), 201


@admin_bp.get("/worksheets/<int:worksheet_id>")
@role_required("ta")
def get_worksheet(worksheet_id):
    """A single assignment by id, with no section/class in the URL — the
    editor (server/routes AssignmentsPage → .../:worksheetId/edit) only
    ever needs the worksheet itself, not which section someone clicked in
    from, now that assignments belong to the class rather than a section.
    """
    worksheet = Worksheet.query.get_or_404(worksheet_id)
    error = require_class_access(get_current_user(), worksheet.klass)
    if error:
        return error
    return jsonify(worksheet=_serialize_worksheet(worksheet))


@admin_bp.put("/worksheets/<int:worksheet_id>")
@role_required("ta")
def update_worksheet(worksheet_id):
    worksheet = Worksheet.query.get_or_404(worksheet_id)
    error = require_class_access(get_current_user(), worksheet.klass)
    if error:
        return error
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify(error="title is required"), 400
    worksheet.title = title
    worksheet.description = (data.get("description") or "").strip()
    if "is_published" in data:
        worksheet.is_published = bool(data.get("is_published"))
    db.session.commit()
    return jsonify(worksheet=_serialize_worksheet(worksheet))


@admin_bp.post("/worksheets/<int:worksheet_id>/publish")
@role_required("ta")
def publish_worksheet(worksheet_id):
    worksheet = Worksheet.query.get_or_404(worksheet_id)
    error = require_class_access(get_current_user(), worksheet.klass)
    if error:
        return error
    worksheet.is_published = True
    db.session.commit()
    return jsonify(worksheet=_serialize_worksheet(worksheet))


@admin_bp.post("/worksheets/<int:worksheet_id>/unpublish")
@role_required("ta")
def unpublish_worksheet(worksheet_id):
    worksheet = Worksheet.query.get_or_404(worksheet_id)
    error = require_class_access(get_current_user(), worksheet.klass)
    if error:
        return error
    worksheet.is_published = False
    db.session.commit()
    return jsonify(worksheet=_serialize_worksheet(worksheet))


@admin_bp.delete("/worksheets/<int:worksheet_id>")
@role_required("ta")
def delete_worksheet(worksheet_id):
    worksheet = Worksheet.query.get_or_404(worksheet_id)
    error = require_class_access(get_current_user(), worksheet.klass)
    if error:
        return error
    _delete_worksheets_cascade([worksheet.id])
    db.session.commit()
    return jsonify(ok=True)


GRADING_MODES = ("simple", "doctest", "pltest", "discussion")


def _validate_reference_solution(grading_mode, setup_code, test_code, reference_solution):
    """Runs `reference_solution` through the real sandboxed grader against
    `test_code` (already resolved — auto-generated for 'simple', hand-written
    for 'pltest', unused for 'doctest'). Returns (None) on success, or
    (response, status) with the specific failure on rejection — shared by
    create_question and update_question so both save paths get the same
    authoring-typo safety net. Not called at all for 'discussion' questions,
    which have no code to validate.
    """

    class _ValidationTarget:
        pass

    validation_target = _ValidationTarget()
    validation_target.setup_code = setup_code
    validation_target.test_code = test_code
    validation_target.grading_mode = grading_mode

    results = grading_service.run_grader(validation_target, reference_solution)
    if results.get("error"):
        return jsonify(error=f"Reference solution failed to run: {results['error']}"), 400
    if grading_mode == "doctest" and results.get("total_count") == 0:
        return (
            jsonify(error="No doctest examples (>>> ...) were found in the starter code's docstrings."),
            400,
        )
    if results.get("passed_count") != results.get("total_count"):
        failures = [t for t in results.get("test_results", []) if not t["passed"]]
        return (
            jsonify(
                error="Your reference solution doesn't pass its own test cases.",
                failing_cases=failures,
            ),
            400,
        )
    return None


def _question_fields_from_request(data):
    """Shared required-field extraction + validation for create/update.

    Branches on grading_mode: 'discussion' questions are pure prompt +
    optional solution write-up, with no code at all. The other three modes
    all need starter_code + a reference solution, and additionally: 'simple'
    needs test_cases (test_code is generated from them), 'pltest' needs
    hand-written test_code, and 'doctest' needs neither (it grades the
    student's own docstring >>> examples).
    """
    title = (data.get("title") or "").strip()
    prompt = (data.get("prompt") or "").strip()
    grading_mode = data.get("grading_mode") or "simple"
    solution_markdown = (data.get("solution_markdown") or "").strip() or None

    if not title or not prompt:
        return None, (jsonify(error="title and prompt are required"), 400)
    if grading_mode not in GRADING_MODES:
        return None, (jsonify(error=f"grading_mode must be one of: {', '.join(GRADING_MODES)}"), 400)

    if grading_mode == "discussion":
        return {
            "title": title,
            "prompt": prompt,
            "grading_mode": grading_mode,
            "starter_code": "",
            "setup_code": "",
            "reference_solution": None,
            "test_cases": None,
            "test_code": "",
            "solution_markdown": solution_markdown,
        }, None

    starter_code = data.get("starter_code") or ""
    reference_solution = data.get("reference_solution") or ""
    setup_code = data.get("setup_code") or ""
    test_cases = data.get("test_cases") or []
    test_code = data.get("test_code") or ""

    if not starter_code.strip():
        return None, (jsonify(error="starter_code is required for autograded questions"), 400)
    if not reference_solution.strip():
        return None, (jsonify(error="a reference (passing) solution is required"), 400)

    if grading_mode == "simple":
        if not isinstance(test_cases, list) or len(test_cases) == 0:
            return None, (jsonify(error="at least one test case is required"), 400)
        for case in test_cases:
            if not isinstance(case, dict) or not (case.get("call") or "").strip() or "expected" not in case:
                return None, (jsonify(error="each test case needs a call and an expected value"), 400)
    elif grading_mode == "pltest":
        if not test_code.strip():
            return None, (jsonify(error="test code is required for custom-test questions"), 400)

    return {
        "title": title,
        "prompt": prompt,
        "grading_mode": grading_mode,
        "starter_code": starter_code,
        "reference_solution": reference_solution,
        "setup_code": setup_code,
        "test_cases": test_cases if grading_mode == "simple" else None,
        "test_code": test_code if grading_mode == "pltest" else "",
        "solution_markdown": solution_markdown,
    }, None


def _resolve_test_code(fields):
    if fields["grading_mode"] == "simple":
        return generate_simple_test_code(fields["test_cases"])
    return fields["test_code"]


@admin_bp.post("/worksheets/<int:worksheet_id>/questions")
@role_required("ta")
def create_question(worksheet_id):
    """The guided question-authoring form: title, problem description, and
    (for the three autograded modes) embedded problem code plus a reference
    "passing solution". The reference solution is run through the real
    sandboxed grader before saving — if it doesn't pass, the save is
    rejected with the specific failure, catching authoring typos before
    students ever see them. 'discussion' questions skip all of that: no
    code, no autograder, just a prompt (and an optional solution write-up).
    """
    worksheet = Worksheet.query.get_or_404(worksheet_id)
    error = require_class_access(get_current_user(), worksheet.klass)
    if error:
        return error
    data = request.get_json(silent=True) or {}

    fields, error = _question_fields_from_request(data)
    if error:
        return error

    test_code = _resolve_test_code(fields)
    if fields["grading_mode"] != "discussion":
        error = _validate_reference_solution(
            fields["grading_mode"], fields["setup_code"], test_code, fields["reference_solution"]
        )
        if error:
            return error

    next_order_index = (
        db.session.query(func.max(Question.order_index)).filter_by(worksheet_id=worksheet.id).scalar()
    )
    next_order_index = 0 if next_order_index is None else next_order_index + 1

    question = Question(
        worksheet_id=worksheet.id,
        order_index=next_order_index,
        title=fields["title"],
        prompt=fields["prompt"],
        starter_code=fields["starter_code"],
        solution_markdown=fields["solution_markdown"],
        setup_code=fields["setup_code"],
        test_code=test_code,
        grading_mode=fields["grading_mode"],
        test_cases_json=json.dumps(fields["test_cases"]) if fields["test_cases"] is not None else None,
        reference_solution=fields["reference_solution"],
    )
    db.session.add(question)
    db.session.commit()

    return jsonify(question=_serialize_question_detail(question)), 201


@admin_bp.put("/questions/<int:question_id>")
@role_required("ta")
def update_question(question_id):
    """Re-validates the (possibly edited) reference solution before saving,
    same safety net as creation. order_index and worksheet_id are untouched
    here — reordering is a separate endpoint
    (PUT /worksheets/:id/questions/reorder).
    """
    question = Question.query.get_or_404(question_id)
    worksheet = Worksheet.query.get_or_404(question.worksheet_id)
    error = require_class_access(get_current_user(), worksheet.klass)
    if error:
        return error
    data = request.get_json(silent=True) or {}

    fields, error = _question_fields_from_request(data)
    if error:
        return error

    test_code = _resolve_test_code(fields)
    if fields["grading_mode"] != "discussion":
        error = _validate_reference_solution(
            fields["grading_mode"], fields["setup_code"], test_code, fields["reference_solution"]
        )
        if error:
            return error

    question.title = fields["title"]
    question.prompt = fields["prompt"]
    question.starter_code = fields["starter_code"]
    question.solution_markdown = fields["solution_markdown"]
    question.setup_code = fields["setup_code"]
    question.test_code = test_code
    question.grading_mode = fields["grading_mode"]
    question.test_cases_json = json.dumps(fields["test_cases"]) if fields["test_cases"] is not None else None
    question.reference_solution = fields["reference_solution"]
    db.session.commit()

    return jsonify(question=_serialize_question_detail(question))


@admin_bp.delete("/questions/<int:question_id>")
@role_required("ta")
def delete_question(question_id):
    """Deletes a question and renumbers the remaining ones' order_index to
    stay contiguous. Known rough edge (accepted, not remapped): a group
    currently sitting past the deleted index will see its
    current_question_index now point at a shifted question.
    """
    question = Question.query.get_or_404(question_id)
    worksheet = Worksheet.query.get_or_404(question.worksheet_id)
    error = require_class_access(get_current_user(), worksheet.klass)
    if error:
        return error
    worksheet_id = question.worksheet_id

    TestRun.query.filter_by(question_id=question.id).delete()
    Attempt.query.filter_by(question_id=question.id).delete()
    Rating.query.filter_by(question_id=question.id).delete()
    GroupQuestionState.query.filter_by(question_id=question.id).delete()
    db.session.delete(question)
    db.session.commit()

    remaining = Question.query.filter_by(worksheet_id=worksheet_id).order_by(Question.order_index).all()
    for i, q in enumerate(remaining):
        q.order_index = i
    db.session.commit()

    return jsonify(ok=True)


@admin_bp.put("/worksheets/<int:worksheet_id>/questions/reorder")
@role_required("ta")
def reorder_questions(worksheet_id):
    worksheet = Worksheet.query.get_or_404(worksheet_id)
    error = require_class_access(get_current_user(), worksheet.klass)
    if error:
        return error
    data = request.get_json(silent=True) or {}
    order = data.get("order")
    if not isinstance(order, list) or not order:
        return jsonify(error="order must be a non-empty list of question ids"), 400

    questions = Question.query.filter_by(worksheet_id=worksheet_id).all()
    if sorted(order) != sorted(q.id for q in questions):
        return jsonify(error="order must contain exactly this worksheet's question ids"), 400

    # Two-phase: the (worksheet_id, order_index) unique constraint means
    # writing final indexes directly can collide mid-transaction with
    # another row's still-current index (e.g. reversing [0,1,2]). Push
    # everything out of the live range first, then assign final values.
    by_id = {q.id: q for q in questions}
    for q in questions:
        q.order_index = -(q.order_index + 1)
    db.session.flush()
    for index, question_id in enumerate(order):
        by_id[question_id].order_index = index
    db.session.commit()

    return jsonify(questions=[_serialize_question_detail(q) for q in sorted(questions, key=lambda q: q.order_index)])


@admin_bp.get("/worksheets/<int:worksheet_id>/questions")
@role_required("ta")
def list_questions(worksheet_id):
    """TA-only: every question on an assignment with full authoring detail
    (test cases, reference solution, expected output) — a TA is trusted
    with the answers, unlike the student-facing /groups/:id/state payload
    which deliberately withholds them until earned.
    """
    worksheet = Worksheet.query.get_or_404(worksheet_id)
    error = require_class_access(get_current_user(), worksheet.klass)
    if error:
        return error
    questions = Question.query.filter_by(worksheet_id=worksheet_id).order_by(Question.order_index).all()
    return jsonify(questions=[_serialize_question_detail(q) for q in questions])


@admin_bp.get("/worksheets/<int:worksheet_id>/grades")
@role_required("ta")
def worksheet_grades(worksheet_id):
    """Per-group pass/fail totals for this assignment, from the same
    TestRun data every "Run tests" already records. "Passed" means the
    group ever got every test case to pass (advance_service.
    has_ever_passed_tests) — not just their latest submission, so a group
    optimizing an already-passing solution doesn't see their grade regress
    if a later attempt happens to fail.
    """
    worksheet = Worksheet.query.get_or_404(worksheet_id)
    error = require_class_access(get_current_user(), worksheet.klass)
    if error:
        return error
    questions = Question.query.filter_by(worksheet_id=worksheet_id).order_by(Question.order_index).all()
    # This assignment is shared across every section of its class, so
    # "every group working on it" spans all of those sections, not one.
    groups = Group.query.join(Section, Group.section_id == Section.id).filter(Section.class_id == worksheet.class_id).all()
    # Exclude a TA/admin's own "View as student" solo group (work_individually,
    # server/blueprints/sections.py) — a staff sanity-check run through an
    # assignment isn't a real student attempt and shouldn't show up in grades.
    staff_group_ids = {
        m.group_id
        for m in GroupMembership.query.join(User, GroupMembership.user_id == User.id)
        .filter(User.role.in_(("ta", "admin")))
        .all()
    }
    groups = [g for g in groups if g.id not in staff_group_ids]

    payload = []
    for group in groups:
        questions_attempted = 0
        questions_passed = 0
        for question in questions:
            latest_run = (
                TestRun.query.filter_by(group_id=group.id, question_id=question.id, source="shared")
                .order_by(TestRun.created_at.desc())
                .first()
            )
            if latest_run is None:
                continue
            questions_attempted += 1
            if advance_service.has_ever_passed_tests(group.id, question.id):
                questions_passed += 1
        payload.append(
            {
                "group_id": group.id,
                "name": group.name,
                "is_individual": group.is_individual,
                "questions_passed": questions_passed,
                "questions_attempted": questions_attempted,
                "total_questions": len(questions),
            }
        )
    return jsonify(groups=payload)


def _slugify(title):
    slug = "".join(c.lower() if c.isalnum() else "-" for c in title)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "assignment"


def _serialize_group(group):
    return {"id": group.id, "number": group.number, "name": group.name, "section_id": group.section_id}


def _serialize_worksheet(worksheet):
    return {
        "id": worksheet.id,
        "slug": worksheet.slug,
        "title": worksheet.title,
        "description": worksheet.description,
        "is_published": worksheet.is_published,
    }


def _serialize_question_detail(question):
    test_cases = json.loads(question.test_cases_json) if question.test_cases_json else None
    return {
        "id": question.id,
        "order_index": question.order_index,
        "title": question.title,
        "prompt": question.prompt,
        "starter_code": question.starter_code,
        "setup_code": question.setup_code,
        "expected_output": question.expected_output,
        "grading_mode": question.grading_mode,
        "test_cases": test_cases,
        "test_code": question.test_code,
        "reference_solution": question.reference_solution,
        "solution_markdown": question.solution_markdown,
    }
