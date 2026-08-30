from server.extensions import db
from server.utils import utcnow


class TestRun(db.Model):
    """One autograder invocation. `source` distinguishes a run against the
    group's shared editor code from a run against a student's private
    scratch editor — see server/services/grading.py.

    Grading itself happens out-of-process (server/services/grading_jobs.py,
    run by server/worker.py via RQ) so a Docker-bound submission doesn't
    block a web worker. A row is created with status="pending" the moment
    the run is accepted and filled in by the worker when Docker finishes —
    see GET /groups/:id/run-tests/:test_run_id in server/blueprints/groups.py.
    """

    __tablename__ = "test_runs"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
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

    user = db.relationship("User")
