from server.extensions import db
from server.utils import utcnow


class Worksheet(db.Model):
    """An assignment within a Class (server/models/klass.py) — a class has
    many of these over time, shared across every Section under it, created
    by a TA via the guided question-authoring form or the git-authored
    content pipeline (server/content/loader.py).
    """

    __tablename__ = "worksheets"

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    # Drafts (the default) are only visible to TAs — see
    # server/blueprints/sections.py:section_worksheets and
    # server/blueprints/groups.py:get_state — so a TA can build an
    # assignment out over time before releasing it to students.
    is_published = db.Column(db.Boolean, default=False, nullable=False)

    klass = db.relationship("Class", backref=db.backref("worksheets", lazy="dynamic"))


class Question(db.Model):
    __tablename__ = "questions"
    __table_args__ = (db.UniqueConstraint("worksheet_id", "order_index"),)

    id = db.Column(db.Integer, primary_key=True)
    worksheet_id = db.Column(db.Integer, db.ForeignKey("worksheets.id"), nullable=False)
    order_index = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(160), nullable=False)
    prompt = db.Column(db.Text, nullable=False)  # markdown
    starter_code = db.Column(db.Text, default="")
    # Nullable: the predict-and-compare flow (client hides it when this is
    # empty) doesn't apply to "write this function" doctest-graded
    # questions the way it does to "trace this code" questions.
    expected_output = db.Column(db.Text, nullable=True)
    language = db.Column(db.String(20), default="python")
    solution_markdown = db.Column(db.Text, nullable=True)

    # Autograder fields (server/services/grading.py). setup_code is a shared
    # preamble (e.g. the Tree class def) executed before both setup and
    # student code. grading_mode selects which harness path runs in the
    # grader container: 'pltest' expects test_code defining a
    # `class Test(PLTestCase)` (grader/harness/pl_unit_test.py); 'doctest'
    # ignores test_code and instead runs the >>> examples already in the
    # student's own function docstrings (grader/harness/doctest_runner.py);
    # 'discussion' has no autograder at all (no starter_code/test_code) —
    # a conceptual/paper question, e.g. an environment-diagram trace.
    setup_code = db.Column(db.Text, default="")
    test_code = db.Column(db.Text, default="")
    grading_mode = db.Column(db.String(20), nullable=False, default="pltest")

    # 'simple' mode (server/services/test_case_grading.py): test_cases_json
    # is a list of {call, expected} pairs authored via the guided TA form —
    # test_code is auto-generated from it rather than hand-written.
    # reference_solution is the TA's "passing solution", used to validate
    # test_cases_json at authoring time and never shown to students.
    test_cases_json = db.Column(db.Text, nullable=True)
    reference_solution = db.Column(db.Text, nullable=True)
