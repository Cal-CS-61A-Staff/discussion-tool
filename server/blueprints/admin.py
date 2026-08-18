import json
from datetime import date

from flask import Blueprint, jsonify, request
from sqlalchemy import func

from server.auth import role_required
from server.extensions import db
from server.models.attempt import Attempt
from server.models.group import Group, GroupAssignmentProgress, GroupMembership, GroupQuestionState
from server.models.rating import Rating
from server.models.section import Section
from server.models.test_run import TestRun
from server.models.worksheet import Question, Worksheet
from server.services import grading as grading_service
from server.services.test_case_grading import generate_simple_test_code

admin_bp = Blueprint("admin", __name__)

MAX_GROUPS_PER_CREATE_CALL = 50


@admin_bp.post("/sections/<int:section_id>/groups")
@role_required("ta")
def create_groups(section_id):
    section = Section.query.get_or_404(section_id)
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


@admin_bp.post("/sections/<int:section_id>/worksheets")
@role_required("ta")
def create_worksheet(section_id):
    Section.query.get_or_404(section_id)
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
        section_id=section_id,
        slug=slug,
        title=title,
        description=(data.get("description") or "").strip(),
        due_date=_parse_due_date(data.get("due_date")),
    )
    db.session.add(worksheet)
    db.session.commit()

    return jsonify(worksheet=_serialize_worksheet(worksheet)), 201


@admin_bp.put("/worksheets/<int:worksheet_id>")
@role_required("ta")
def update_worksheet(worksheet_id):
    worksheet = Worksheet.query.get_or_404(worksheet_id)
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify(error="title is required"), 400
    worksheet.title = title
    worksheet.description = (data.get("description") or "").strip()
    worksheet.due_date = _parse_due_date(data.get("due_date"))
    if "is_published" in data:
        worksheet.is_published = bool(data.get("is_published"))
    db.session.commit()
    return jsonify(worksheet=_serialize_worksheet(worksheet))


@admin_bp.post("/worksheets/<int:worksheet_id>/publish")
@role_required("ta")
def publish_worksheet(worksheet_id):
    worksheet = Worksheet.query.get_or_404(worksheet_id)
    worksheet.is_published = True
    db.session.commit()
    return jsonify(worksheet=_serialize_worksheet(worksheet))


@admin_bp.post("/worksheets/<int:worksheet_id>/unpublish")
@role_required("ta")
def unpublish_worksheet(worksheet_id):
    worksheet = Worksheet.query.get_or_404(worksheet_id)
    worksheet.is_published = False
    db.session.commit()
    return jsonify(worksheet=_serialize_worksheet(worksheet))


@admin_bp.delete("/worksheets/<int:worksheet_id>")
@role_required("ta")
def delete_worksheet(worksheet_id):
    worksheet = Worksheet.query.get_or_404(worksheet_id)
    question_ids = [
        q.id for q in Question.query.filter_by(worksheet_id=worksheet.id).with_entities(Question.id).all()
    ]
    if question_ids:
        TestRun.query.filter(TestRun.question_id.in_(question_ids)).delete(synchronize_session=False)
        Attempt.query.filter(Attempt.question_id.in_(question_ids)).delete(synchronize_session=False)
        Rating.query.filter(Rating.question_id.in_(question_ids)).delete(synchronize_session=False)
        GroupQuestionState.query.filter(GroupQuestionState.question_id.in_(question_ids)).delete(
            synchronize_session=False
        )
    Question.query.filter_by(worksheet_id=worksheet.id).delete()
    GroupAssignmentProgress.query.filter_by(worksheet_id=worksheet.id).delete()
    db.session.delete(worksheet)
    db.session.commit()
    return jsonify(ok=True)


def _validate_reference_solution(setup_code, test_cases, reference_solution):
    """Runs `reference_solution` through the real sandboxed grader against
    test_code generated from `test_cases`. Returns (test_code, None) on
    success, or (None, (response, status)) with the specific failure on
    rejection — shared by create_question and update_question so both save
    paths get the same authoring-typo safety net.
    """
    test_code = generate_simple_test_code(test_cases)

    class _ValidationTarget:
        pass

    validation_target = _ValidationTarget()
    validation_target.setup_code = setup_code
    validation_target.test_code = test_code
    validation_target.grading_mode = "pltest"

    results = grading_service.run_grader(validation_target, reference_solution)
    if results.get("error"):
        return None, (jsonify(error=f"Reference solution failed to run: {results['error']}"), 400)
    if results.get("passed_count") != results.get("total_count"):
        failures = [t for t in results.get("test_results", []) if not t["passed"]]
        return None, (
            jsonify(
                error="Your reference solution doesn't pass its own test cases.",
                failing_cases=failures,
            ),
            400,
        )
    return test_code, None


def _question_fields_from_request(data):
    """Shared required-field extraction + validation for create/update."""
    title = (data.get("title") or "").strip()
    prompt = (data.get("prompt") or "").strip()
    starter_code = data.get("starter_code") or ""
    reference_solution = data.get("reference_solution") or ""
    setup_code = data.get("setup_code") or ""
    test_cases = data.get("test_cases") or []

    if not title or not prompt or not starter_code.strip():
        return None, (jsonify(error="title, prompt, and starter_code are required"), 400)
    if not reference_solution.strip():
        return None, (jsonify(error="a reference (passing) solution is required"), 400)
    if not isinstance(test_cases, list) or len(test_cases) == 0:
        return None, (jsonify(error="at least one test case is required"), 400)
    for case in test_cases:
        if not isinstance(case, dict) or not (case.get("call") or "").strip() or "expected" not in case:
            return None, (jsonify(error="each test case needs a call and an expected value"), 400)

    return {
        "title": title,
        "prompt": prompt,
        "starter_code": starter_code,
        "reference_solution": reference_solution,
        "setup_code": setup_code,
        "test_cases": test_cases,
    }, None


@admin_bp.post("/worksheets/<int:worksheet_id>/questions")
@role_required("ta")
def create_question(worksheet_id):
    """The guided question-authoring form: title/difficulty, problem
    description, embedded problem code, a repeatable test-case list, and a
    reference "passing solution". The reference solution is run through the
    real sandboxed grader against the generated test code *before* saving —
    if it doesn't pass its own test cases, the save is rejected with the
    specific failure, catching authoring typos before students ever see them.
    """
    worksheet = Worksheet.query.get_or_404(worksheet_id)
    data = request.get_json(silent=True) or {}

    fields, error = _question_fields_from_request(data)
    if error:
        return error

    test_code, error = _validate_reference_solution(
        fields["setup_code"], fields["test_cases"], fields["reference_solution"]
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
        difficulty=(data.get("difficulty") or None),
        solution_markdown=(data.get("solution_markdown") or None),
        setup_code=fields["setup_code"],
        test_code=test_code,
        grading_mode="simple",
        test_cases_json=json.dumps(fields["test_cases"]),
        reference_solution=fields["reference_solution"],
    )
    db.session.add(question)
    db.session.commit()

    return jsonify(question=_serialize_question_detail(question)), 201


@admin_bp.put("/questions/<int:question_id>")
@role_required("ta")
def update_question(question_id):
    """Re-validates the (possibly edited) reference solution against the
    (possibly edited) test cases before saving, same safety net as creation.
    order_index and worksheet_id are untouched here — reordering is a
    separate endpoint (PUT /worksheets/:id/questions/reorder).
    """
    question = Question.query.get_or_404(question_id)
    data = request.get_json(silent=True) or {}

    fields, error = _question_fields_from_request(data)
    if error:
        return error

    test_code, error = _validate_reference_solution(
        fields["setup_code"], fields["test_cases"], fields["reference_solution"]
    )
    if error:
        return error

    question.title = fields["title"]
    question.prompt = fields["prompt"]
    question.starter_code = fields["starter_code"]
    question.difficulty = data.get("difficulty") or None
    question.solution_markdown = data.get("solution_markdown") or None
    question.setup_code = fields["setup_code"]
    question.test_code = test_code
    question.grading_mode = "simple"
    question.test_cases_json = json.dumps(fields["test_cases"])
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
    Worksheet.query.get_or_404(worksheet_id)
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
    Worksheet.query.get_or_404(worksheet_id)
    questions = Question.query.filter_by(worksheet_id=worksheet_id).order_by(Question.order_index).all()
    return jsonify(questions=[_serialize_question_detail(q) for q in questions])


@admin_bp.get("/worksheets/<int:worksheet_id>/grades")
@role_required("ta")
def worksheet_grades(worksheet_id):
    """Per-group point totals for this assignment, from the same points
    data every "Run tests" already records (TestRun.total_points/max_points,
    populated by the @points(1)-per-test-case grader output) — no new
    grading logic, just an aggregation over the latest shared run per
    (group, question).
    """
    worksheet = Worksheet.query.get_or_404(worksheet_id)
    questions = Question.query.filter_by(worksheet_id=worksheet_id).order_by(Question.order_index).all()
    groups = Group.query.filter_by(section_id=worksheet.section_id).all()

    payload = []
    for group in groups:
        points_earned = 0.0
        points_possible = 0.0
        questions_attempted = 0
        for question in questions:
            latest_run = (
                TestRun.query.filter_by(group_id=group.id, question_id=question.id, source="shared")
                .order_by(TestRun.created_at.desc())
                .first()
            )
            if latest_run is None:
                continue
            questions_attempted += 1
            points_earned += latest_run.total_points
            points_possible += latest_run.max_points
        payload.append(
            {
                "group_id": group.id,
                "name": group.name,
                "is_individual": group.is_individual,
                "points_earned": points_earned,
                "points_possible": points_possible,
                "questions_attempted": questions_attempted,
                "total_questions": len(questions),
            }
        )
    return jsonify(groups=payload)


def _parse_due_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


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
        "due_date": worksheet.due_date.isoformat() if worksheet.due_date else None,
        "is_published": worksheet.is_published,
    }


def _serialize_question_detail(question):
    test_cases = json.loads(question.test_cases_json) if question.test_cases_json else None
    return {
        "id": question.id,
        "order_index": question.order_index,
        "title": question.title,
        "difficulty": question.difficulty,
        "prompt": question.prompt,
        "starter_code": question.starter_code,
        "setup_code": question.setup_code,
        "expected_output": question.expected_output,
        "grading_mode": question.grading_mode,
        "test_cases": test_cases,
        "reference_solution": question.reference_solution,
        "solution_markdown": question.solution_markdown,
    }
