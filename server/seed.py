import json
import os

from server.content.loader import discover_worksheet_dirs, load_worksheet_from_dir
from server.extensions import db
from server.models.group import Group
from server.models.section import Section
from server.models.worksheet import Question, Worksheet

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT_DIR = os.path.join(REPO_ROOT, "content")

DEMO_GROUP_COUNT = 4


def seed_db():
    _seed_json_fixtures()
    _seed_content_worksheets()


def _seed_json_fixtures():
    with open(os.path.join(FIXTURES_DIR, "tree_map_worksheet.json")) as f:
        data = json.load(f)
    _upsert_worksheet(data)


def _seed_content_worksheets():
    for worksheet_dir in discover_worksheet_dirs(CONTENT_DIR):
        data = load_worksheet_from_dir(worksheet_dir)
        _upsert_worksheet(data)


def _upsert_worksheet(data):
    section = _upsert_class(data["class_course_name"], data["class_name"])

    worksheet = Worksheet.query.filter_by(slug=data["slug"]).first()
    if worksheet is None:
        # Seeded/git-authored content is demo material meant to be usable
        # right away — unlike a freshly-created TA-form assignment (which
        # defaults to draft so it can be built out before release), this
        # starts published.
        worksheet = Worksheet(
            section_id=section.id,
            slug=data["slug"],
            title=data["title"],
            description=data.get("description", ""),
            is_published=True,
        )
        db.session.add(worksheet)
        db.session.flush()
    else:
        worksheet.section_id = section.id
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
        question.difficulty = q.get("difficulty")
        question.setup_code = q.get("setup_code", "")
        question.test_code = q.get("test_code", "")
        question.grading_mode = q.get("grading_mode", "pltest")
        question.solution_markdown = q.get("solution_markdown")

    db.session.commit()
    print(f"Seeded assignment '{worksheet.title}' in class '{section.course_name} / {section.name}'.")


def _upsert_class(course_name, name):
    section = Section.query.filter_by(course_name=course_name, name=name).first()
    if section is None:
        section = Section(course_name=course_name, name=name)
        db.session.add(section)
        db.session.commit()

    existing_groups = Group.query.filter_by(section_id=section.id, is_individual=False).count()
    if existing_groups == 0:
        for number in range(1, DEMO_GROUP_COUNT + 1):
            db.session.add(Group(section_id=section.id, number=number, name=f"Group {number}"))
        db.session.commit()
        print(f"  created demo groups 1-{DEMO_GROUP_COUNT} for '{course_name} / {name}'")

    return section
