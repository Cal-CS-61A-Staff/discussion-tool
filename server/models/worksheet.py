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
    # Short unguessable slug in the student share link (/w/<share_code>).
    # Set the first time the worksheet is published; the only way a
    # student (who has no account and no class enrollment) reaches it.
    share_code = db.Column(db.String(12), unique=True, nullable=True)

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

    # 'coding' (the default) is the historic behaviour: an embedded code
    # editor graded by the sandboxed autograder via grading_mode below.
    # Every other value is a non-code answer/content widget authored via
    # the guided TA form — multiple_choice, dropdown, fill_blank_code,
    # fill_blank_markdown, short_answer, text_markdown, plain_text, image,
    # iframe. For those, grading_mode is forced to 'discussion' (a compat
    # shim so the code/grader guards elsewhere naturally skip them) and
    # content_json holds the type-specific config. See
    # server/services/response_grading.py for the schema per type and
    # server/blueprints/admin.py:PROBLEM_TYPES for the allowed set.
    problem_type = db.Column(db.String(30), nullable=False, default="coding")
    # JSON-in-Text (same guarded json.dumps/json.loads pattern as
    # test_cases_json): {options:[...]}, {template, blanks:[...]},
    # {answer, accept, case_sensitive}, {url, alt}, etc. NULL for 'coding'.
    content_json = db.Column(db.Text, nullable=True)

    # Autograder fields. Grading runs in the browser now (Pyodide —
    # client/src/pyodide/harness.py). setup_code is a shared preamble (e.g.
    # the Tree class def) executed before both setup and student code.
    # grading_mode selects which harness path runs: 'pltest' expects
    # test_code defining a `class Test(PLTestCase)`; 'simple' generates that
    # test_code from TA {call, expected} pairs
    # (server/services/test_case_grading.py); 'doctest' ignores test_code
    # and runs the >>> examples already in the student's own function
    # docstrings; 'discussion' has no autograder at all (no
    # starter_code/test_code) — a conceptual/paper question.
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

    # Optional, works on ANY problem_type. JSON-in-Text:
    #   {"mode": "output", "setup": str, "doctest": str,
    #    "items": [{"code", "expected"}]}   -- items parsed + sandbox-verified
    #                                          on save; one drawn at random per
    #                                          group; student predicts its output
    #   {"mode": "written", "prompt": str}  -- a free-text reflection prompt
    # When set it gates advancing (server/services/advance.py); NULL = no
    # prediction. Replaces the old expected_output-driven coding quiz.
    prediction_json = db.Column(db.Text, nullable=True)
    # Optional, any problem_type: Python source rendered as an embedded
    # pythontutor.com environment-diagram stepper below the prompt.
    python_tutor_code = db.Column(db.Text, nullable=True)
