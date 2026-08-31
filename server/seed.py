import json
import os

from server.content.loader import discover_worksheet_dirs, load_worksheet_from_dir
from server.extensions import db
from server.models.group import Group
from server.models.klass import Class
from server.models.section import Section
from server.models.worksheet import Question, Worksheet

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT_DIR = os.path.join(REPO_ROOT, "content")

DEMO_GROUP_COUNT = 4


def seed_db():
    _seed_json_fixtures()
    _seed_content_worksheets()
    print(
        "\nNote: seeded classes have no TA assigned yet (Section.ta_user_id). "
        "Sign in once as a TA to create that account, then create an admin "
        "(`flask create-admin <name>`), sign in as that admin, and assign "
        "the TA to a class from the Admin page — see README.md."
    )


def _seed_json_fixtures():
    with open(os.path.join(FIXTURES_DIR, "tree_map_worksheet.json")) as f:
        data = json.load(f)
    _upsert_worksheet(data)


def _seed_content_worksheets():
    for worksheet_dir in discover_worksheet_dirs(CONTENT_DIR):
        data = load_worksheet_from_dir(worksheet_dir)
        _upsert_worksheet(data)


def _upsert_worksheet(data):
    # class_course_name/class_name name the class and one of its sections —
    # the assignment itself belongs only to the class (shared across every
    # section in it); the section is upserted purely so this demo content
    # has somewhere to put its demo groups (see _upsert_section).
    klass = _upsert_class(data["class_course_name"])
    _upsert_section(klass, data["class_name"])

    worksheet = Worksheet.query.filter_by(slug=data["slug"]).first()
    if worksheet is None:
        # Seeded/git-authored content is demo material meant to be usable
        # right away — unlike a freshly-created TA-form assignment (which
        # defaults to draft so it can be built out before release), this
        # starts published.
        worksheet = Worksheet(
            class_id=klass.id,
            slug=data["slug"],
            title=data["title"],
            description=data.get("description", ""),
            is_published=True,
        )
        db.session.add(worksheet)
        db.session.flush()
    else:
        worksheet.class_id = klass.id
        worksheet.title = data["title"]
        worksheet.description = data.get("description", "")

    for q in data["questions"]:
        question = Question.query.filter_by(worksheet_id=worksheet.id, order_index=q["order_index"]).first()
        if question is None:
            question = Question(worksheet_id=worksheet.id, order_index=q["order_index"])
            db.session.add(question)
        question.title = q["title"]
        question.prompt = q["prompt"]
        question.starter_code = q.get("starter_code", "")
        question.expected_output = q.get("expected_output")
        question.language = q.get("language", "python")
        question.setup_code = q.get("setup_code", "")
        question.test_code = q.get("test_code", "")
        question.grading_mode = q.get("grading_mode", "pltest")
        question.problem_type = q.get("problem_type", "coding")
        question.content_json = q.get("content_json")
        question.solution_markdown = q.get("solution_markdown")

    db.session.commit()
    print(f"Seeded assignment '{worksheet.title}' in class '{klass.course_name}'.")


def _upsert_class(course_name):
    klass = Class.query.filter_by(course_name=course_name).first()
    if klass is None:
        klass = Class(course_name=course_name)
        db.session.add(klass)
        db.session.commit()
    return klass


def _upsert_section(klass, name):
    section = Section.query.filter_by(class_id=klass.id, name=name).first()
    if section is None:
        section = Section(class_id=klass.id, name=name)
        db.session.add(section)
        db.session.commit()

    existing_groups = Group.query.filter_by(section_id=section.id, is_individual=False).count()
    if existing_groups == 0:
        for number in range(1, DEMO_GROUP_COUNT + 1):
            db.session.add(Group(section_id=section.id, number=number, name=f"Group {number}"))
        db.session.commit()
        print(f"  created demo groups 1-{DEMO_GROUP_COUNT} for '{klass.course_name} / {name}'")

    return section
