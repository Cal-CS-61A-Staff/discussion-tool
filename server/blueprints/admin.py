import json

from flask import Blueprint, jsonify, request
from sqlalchemy import func

from server.auth import (
    admin_required,
    get_current_user,
    is_class_staff,
    login_required,
    require_class_access,
    require_section_access,
    role_required,
)
from server.blueprints.sections import _serialize_class, _serialize_section
from server.extensions import db
from server.models.group import (
    Group,
    GroupAssignmentProgress,
    GroupMembership,
    GroupQuestionState,
    ScratchCode,
)
from server.models.group_prediction import GroupPrediction
from server.models.klass import Class, ClassMembership
from server.models.question_response import QuestionResponse
from server.models.rating import Rating
from server.models.section import Section, SectionCoTeacher
from server.models.ta_watch import TaWatchedNumber
from server.models.test_run import TestRun
from server.models.user import User
from server.models.worksheet import Question, Worksheet
from server.services import advance as advance_service
from server.services import response_grading
from server.services.number_spec import format_number_spec, parse_number_spec
from server.services.roster_import import add_admin_by_email, find_user_by_email, import_ta_roster
from server.services.test_case_grading import generate_simple_test_code
from server.utils import generate_join_code

admin_bp = Blueprint("admin", __name__)


@admin_bp.get("/admins")
@admin_required
def list_admins():
    """Admin-only — the current admin (global super-user) accounts, for the
    Admin page's admin list. Per-class staff are managed separately, on the
    class's Rooms page (GET/POST /api/classes/:id/staff)."""
    admins = User.query.filter_by(role="admin").order_by(User.display_name).all()
    return jsonify(admins=[{"id": a.id, "display_name": a.display_name, "email": a.email} for a in admins])


@admin_bp.post("/admins")
@admin_required
def add_admin():
    """Admin-only — grant the 'admin' role to a user, found or created by
    email (+ optional name). 'role' is one column and 'admin' is a strict
    superset of 'ta'/'student' (server/auth.py), so this is additive: a
    promoted TA keeps all their sections and simply gains the admin-only
    actions. Like add_ta above, a not-yet-registered person can be granted
    admin from just their email. This is the in-app path alongside the
    `create-admin` CLI (server/app.py).
    """
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    name = (data.get("name") or "").strip()
    if not email or "@" not in email:
        return jsonify(error="a valid email is required"), 400
    admin = add_admin_by_email(email, name or None)
    return (
        jsonify(admin={"id": admin.id, "display_name": admin.display_name, "email": admin.email, "role": admin.role}),
        201,
    )


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
        if ta is None or not is_class_staff(ta, section.klass):
            return jsonify(error="ta_user_id must be a staff member of this class"), 400
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

    code = generate_join_code()
    while Class.query.filter_by(join_code=code).first() is not None:
        code = generate_join_code()
    klass = Class(course_name=course_name, join_code=code)
    db.session.add(klass)
    db.session.flush()
    # The creating admin gets an explicit staff membership so the class
    # shows up as theirs to manage, not just via the admin super-user path.
    db.session.add(ClassMembership(user_id=user.id, class_id=klass.id, role="staff"))
    db.session.commit()
    return jsonify(klass=_serialize_class(klass, "staff")), 201


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
    return jsonify(klass=_serialize_class(klass, "staff"))


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
        SectionCoTeacher.query.filter(SectionCoTeacher.section_id.in_(section_ids)).delete(synchronize_session=False)
        Section.query.filter(Section.id.in_(section_ids)).delete(synchronize_session=False)

    _delete_class_groups_cascade(klass.id)
    ClassMembership.query.filter_by(class_id=klass.id).delete(synchronize_session=False)
    TaWatchedNumber.query.filter_by(class_id=klass.id).delete(synchronize_session=False)

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


def _delete_class_groups_cascade(class_id):
    """Used by delete_class — wipes every group in the class (and its
    progress/history). Groups are class-scoped now, not per-room, so a
    room deletion never touches them. SQLite FK enforcement is off by
    default in this app, so cascading is done explicitly.
    """
    group_ids = [g.id for g in Group.query.filter_by(class_id=class_id).with_entities(Group.id).all()]
    if not group_ids:
        return
    for model in (TestRun, Rating, GroupQuestionState, ScratchCode, QuestionResponse, GroupPrediction):
        model.query.filter(model.group_id.in_(group_ids)).delete(synchronize_session=False)
    GroupAssignmentProgress.query.filter(GroupAssignmentProgress.group_id.in_(group_ids)).delete(
        synchronize_session=False
    )
    GroupMembership.query.filter(GroupMembership.group_id.in_(group_ids)).delete(synchronize_session=False)
    Group.query.filter_by(class_id=class_id).delete(synchronize_session=False)


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
        for model in (TestRun, Rating, GroupQuestionState, ScratchCode, QuestionResponse, GroupPrediction):
            model.query.filter(model.question_id.in_(question_ids)).delete(synchronize_session=False)
    Question.query.filter(Question.worksheet_id.in_(worksheet_ids)).delete(synchronize_session=False)
    GroupAssignmentProgress.query.filter(GroupAssignmentProgress.worksheet_id.in_(worksheet_ids)).delete(
        synchronize_session=False
    )
    Worksheet.query.filter(Worksheet.id.in_(worksheet_ids)).delete(synchronize_session=False)


@admin_bp.delete("/sections/<int:section_id>")
@admin_required
def delete_section(section_id):
    """Admin-only — deletes the room and its co-teacher records only.
    Groups, progress and history are class-scoped now (server/models/
    group.py) and outlive any room; only deleting the whole class removes
    those (see delete_class above).
    """
    section = Section.query.get_or_404(section_id)
    SectionCoTeacher.query.filter_by(section_id=section.id).delete(synchronize_session=False)
    db.session.delete(section)
    db.session.commit()
    return jsonify(ok=True)


@admin_bp.put("/sections/<int:section_id>/details")
@role_required("ta")
def update_section_details(section_id):
    """Any staff member of the room's class (or an admin) can rename it and
    set which group **numbers** it covers (`assigned_numbers`, a spec like
    "1-8,12" — this seeds a TA's dashboard watch list). Assigning who runs
    the room stays admin-only (assign_section_ta).
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
    if "assigned_numbers" in data:
        section.assigned_numbers = format_number_spec(parse_number_spec(data.get("assigned_numbers") or ""))
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
    if ta is None or not is_class_staff(ta, section.klass):
        return jsonify(error="that person isn't staff of this class — add them as class staff first"), 404
    if ta.id == section.ta_user_id:
        return jsonify(error="that person already runs this room"), 400

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
    """Admin-only — uploads the TA roster CSV: columns `Name, Email,
    Sections` (Sections is one cell, ';'-separated list of section labels).
    Upserts a TA per row (matched by email) and find-or-creates + assigns
    each listed section. See server/services/roster_import.py.
    """
    data = request.get_json(silent=True) or {}
    text = data.get("csv") or ""
    if not text.strip():
        return jsonify(error="csv is required"), 400
    summary = import_ta_roster(text)
    return jsonify(summary=summary)


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
        if worksheet.is_published:
            _ensure_share_code(worksheet)
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
    _ensure_share_code(worksheet)
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

# 'coding' is the historic code-editor + autograder question (grading_mode
# picks the harness path). Everything else is a non-code answer/content
# widget authored via the same guided form; see
# server/services/response_grading.py for each type's content schema.
PROBLEM_TYPES = (
    "coding",
    "multiple_choice",
    "dropdown",
    "fill_blank_code",
    "fill_blank_markdown",
    "short_answer",
    "text_markdown",
    "plain_text",
    "image",
    "iframe",
    "counterexample",
)


# Reference-solution validation and prediction-item resolution both used to
# run the sandboxed Docker grader here at save time. Grading is in-browser
# now (Pyodide — client/src/pyodide/), so the TA editor does both before it
# POSTs: it runs the reference solution against the tests and blocks the
# save on failure, and it resolves each output-prediction call's expected
# output and sends `items` in the payload (shape-checked in
# server/services/response_grading.py:validate_prediction).


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
    problem_type = data.get("problem_type") or "coding"
    grading_mode = data.get("grading_mode") or "simple"
    solution_markdown = (data.get("solution_markdown") or "").strip() or None

    if not title or not prompt:
        return None, (jsonify(error="title and prompt are required"), 400)
    if problem_type not in PROBLEM_TYPES:
        return None, (jsonify(error=f"problem_type must be one of: {', '.join(PROBLEM_TYPES)}"), 400)

    # Optional, on any problem_type.
    clean_prediction, prediction_error = response_grading.validate_prediction(data.get("prediction"))
    if prediction_error:
        return None, (jsonify(error=prediction_error), 400)
    prediction_json = json.dumps(clean_prediction) if clean_prediction else None
    python_tutor_code = (data.get("python_tutor_code") or "").strip() or None
    extras = {"prediction_json": prediction_json, "python_tutor_code": python_tutor_code}

    if problem_type != "coding":
        clean_content, content_error = response_grading.validate_content(problem_type, data.get("content") or {})
        if content_error:
            return None, (jsonify(error=content_error), 400)
        return {
            "title": title,
            "prompt": prompt,
            # grading_mode forced to 'discussion' so the code/grader guards
            # throughout the server naturally skip non-code questions.
            "grading_mode": "discussion",
            "problem_type": problem_type,
            "content_json": json.dumps(clean_content),
            "starter_code": "",
            "setup_code": "",
            "reference_solution": None,
            "test_cases": None,
            "test_code": "",
            "solution_markdown": solution_markdown,
            **extras,
        }, None

    if grading_mode not in GRADING_MODES:
        return None, (jsonify(error=f"grading_mode must be one of: {', '.join(GRADING_MODES)}"), 400)

    if grading_mode == "discussion":
        return {
            "title": title,
            "prompt": prompt,
            "grading_mode": grading_mode,
            "problem_type": "coding",
            "content_json": None,
            "starter_code": "",
            "setup_code": "",
            "reference_solution": None,
            "test_cases": None,
            "test_code": "",
            "solution_markdown": solution_markdown,
            **extras,
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
        "problem_type": "coding",
        "content_json": None,
        "starter_code": starter_code,
        "reference_solution": reference_solution,
        "setup_code": setup_code,
        "test_cases": test_cases if grading_mode == "simple" else None,
        "test_code": test_code if grading_mode == "pltest" else "",
        "solution_markdown": solution_markdown,
        **extras,
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
    "passing solution". The TA editor runs the reference solution against
    the tests in the browser (Pyodide) before it POSTs and blocks the save
    on failure, catching authoring typos before students see them; here we
    just shape-check the fields and the client-resolved prediction `items`.
    'discussion' questions have no code and no autograder — just a prompt
    (and an optional solution write-up).
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
        problem_type=fields["problem_type"],
        content_json=fields["content_json"],
        prediction_json=fields["prediction_json"],
        python_tutor_code=fields["python_tutor_code"],
        test_cases_json=json.dumps(fields["test_cases"]) if fields["test_cases"] is not None else None,
        reference_solution=fields["reference_solution"],
    )
    db.session.add(question)
    db.session.commit()

    return jsonify(question=_serialize_question_detail(question)), 201


@admin_bp.put("/questions/<int:question_id>")
@role_required("ta")
def update_question(question_id):
    """Same as creation: the client has already run the (possibly edited)
    reference solution against the tests in the browser and blocked the
    save on failure. order_index and worksheet_id are untouched here —
    reordering is a separate endpoint
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

    question.title = fields["title"]
    question.prompt = fields["prompt"]
    question.starter_code = fields["starter_code"]
    question.solution_markdown = fields["solution_markdown"]
    question.setup_code = fields["setup_code"]
    question.test_code = test_code
    question.grading_mode = fields["grading_mode"]
    question.problem_type = fields["problem_type"]
    question.content_json = fields["content_json"]
    question.prediction_json = fields["prediction_json"]
    question.python_tutor_code = fields["python_tutor_code"]
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

    for model in (TestRun, Rating, GroupQuestionState, ScratchCode, QuestionResponse, GroupPrediction):
        model.query.filter_by(question_id=question.id).delete()
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


@admin_bp.get("/worksheets/<int:worksheet_id>/participation.csv")
@role_required("ta")
def participation_csv(worksheet_id):
    """The durable participation record: one row per (group, participant),
    computed live for groups still present and merged with the on-disk
    snapshot for any the retention job has already purged
    (server/services/retention.py). Rows disappear
    Config.SESSION_DATA_TTL_DAYS days after a group goes idle.
    """
    import csv
    import io
    import os

    from flask import Response

    from server.config import Config
    from server.services import retention

    worksheet = Worksheet.query.get_or_404(worksheet_id)
    error = require_class_access(get_current_user(), worksheet.klass)
    if error:
        return error

    rows = {
        (r["group_number"], r["participant_name"]): r for r in retention.participation_rows(worksheet)
    }
    snapshot_path = os.path.join(
        Config.RETENTION_SNAPSHOT_DIR,
        retention._slug(worksheet.klass.course_name),
        f"{retention._slug(worksheet.slug)}.csv",
    )
    if os.path.exists(snapshot_path):
        with open(snapshot_path) as f:
            for r in csv.DictReader(f):
                rows.setdefault((r["group_number"], r["participant_name"]), r)

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=retention.CSV_COLUMNS)
    writer.writeheader()
    writer.writerows(sorted(rows.values(), key=lambda r: (str(r["group_number"]), r["participant_name"])))
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{worksheet.slug}-participation.csv"'},
    )


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
    # Groups are class-scoped now — every group in the class is "working on"
    # any of its assignments.
    groups = Group.query.filter_by(class_id=worksheet.class_id).all()
    # Exclude a staff member's own "View as student" solo group — a
    # sanity-check run through an assignment isn't a real student attempt.
    # Staff who enter the student flow get a participant key prefixed
    # "staff-" (server/participant.py). A real student working solo still
    # counts.
    staff_solo_ids = set()
    for g in groups:
        if not g.is_individual:
            continue
        member = GroupMembership.query.filter_by(group_id=g.id).first()
        if member is not None and (member.participant_key or "").startswith("staff-"):
            staff_solo_ids.add(g.id)
    groups = [g for g in groups if g.id not in staff_solo_ids]

    payload = []
    for group in groups:
        questions_attempted = 0
        questions_passed = 0
        for question in questions:
            if (question.problem_type or "coding") != "coding":
                # Non-code questions have no TestRun — a stored group answer
                # is the "attempt", and has_ever_passed_tests knows how to
                # score it (a correct answer for auto-checkable types).
                response = QuestionResponse.query.filter_by(
                    group_id=group.id, question_id=question.id
                ).first()
                if response is None:
                    continue
                questions_attempted += 1
                if advance_service.has_ever_passed_tests(group.id, question.id):
                    questions_passed += 1
                continue
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


def _ensure_share_code(worksheet):
    """The student share link's slug (Worksheet.share_code). Minted the
    first time a worksheet is published and kept stable thereafter — it's
    the only way a student (no account, no enrollment) reaches it."""
    if worksheet.share_code:
        return
    code = generate_join_code(10)
    while Worksheet.query.filter_by(share_code=code).first() is not None:
        code = generate_join_code(10)
    worksheet.share_code = code


def _serialize_worksheet(worksheet):
    return {
        "id": worksheet.id,
        "class_id": worksheet.class_id,
        "slug": worksheet.slug,
        "title": worksheet.title,
        "description": worksheet.description,
        "is_published": worksheet.is_published,
        "share_code": worksheet.share_code,
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
        # TA editor payload — full content incl. answers (a TA is trusted
        # with them, unlike the student /state payload).
        "problem_type": question.problem_type or "coding",
        "content": response_grading.parse_content(question) if (question.problem_type or "coding") != "coding" else None,
        "prediction": json.loads(question.prediction_json) if question.prediction_json else None,
        "python_tutor_code": question.python_tutor_code or "",
        "test_cases": test_cases,
        "test_code": question.test_code,
        "reference_solution": question.reference_solution,
        "solution_markdown": question.solution_markdown,
    }
