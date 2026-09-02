from server.extensions import db
from server.utils import utcnow


class TestRun(db.Model):
    """One autograder invocation. `source` distinguishes a run against the
    group's shared editor code from a run against a student's private
    scratch editor.

    Grading runs in the student's browser (Pyodide — client/src/pyodide/);
    the client POSTs the computed {passed_count, total_count, results_json}
    and the row is written straight away with status="done". The server
    trusts the result, which is acceptable for participation-graded
    discussion — code_snapshot is still stored so a run could be re-graded
    later if that ever changes. See POST /groups/:id/run-tests in
    server/blueprints/groups.py.
    """

    __tablename__ = "test_runs"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    participant_key = db.Column(db.String(40), nullable=False)
    source = db.Column(db.String(10), nullable=False)  # 'shared' | 'scratch'
    # Required before a run is accepted (server/blueprints/groups.py) — a
    # commit-to-a-guess step ahead of every "Run tests", not compared
    # automatically against the real output (there isn't always a single
    # canonical one across grading modes), just recorded.
    prediction_text = db.Column(db.Text, nullable=False)
    code_snapshot = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(10), nullable=False, default="pending")  # 'pending' | 'done'
    passed_count = db.Column(db.Integer, nullable=True)
    total_count = db.Column(db.Integer, nullable=True)
    results_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, index=True)
