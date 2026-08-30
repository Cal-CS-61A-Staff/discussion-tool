"""RQ job bodies — run inside a `flask grading-worker` process (server/app.py),
not the web process that enqueued them (server/services/grading_queue.py).
Each worker process runs one job at a time, so the number of worker
processes you run *is* the concurrent-Docker-container cap — see README
"Grading concurrency".
"""

import json

from server.extensions import db
from server.models.test_run import TestRun
from server.models.worksheet import Question
from server.services import grading as grading_service


def run_grading_job(test_run_id, prediction_feedback, cooldown_seconds):
    """Runs the actual sandboxed grader for a pending TestRun and fills in
    its result columns — mirrors the dict shape server/blueprints/groups.py's
    run_tests used to return directly, since GET .../run-tests/:id (the
    polling endpoint) hands results_json straight back to the frontend.
    """
    try:
        test_run = db.session.get(TestRun, test_run_id)
        if test_run is None:
            return

        question = db.session.get(Question, test_run.question_id)
        results = grading_service.run_grader(question, test_run.code_snapshot)
        results["cooldown_seconds"] = cooldown_seconds
        results["prediction_feedback"] = prediction_feedback

        test_run.passed_count = results.get("passed_count", 0)
        test_run.total_count = results.get("total_count", 0)
        test_run.results_json = json.dumps(results)
        test_run.status = "done"
        db.session.commit()
    except Exception:
        db.session.rollback()
        test_run = db.session.get(TestRun, test_run_id)
        if test_run is not None:
            test_run.passed_count = 0
            test_run.total_count = 0
            test_run.results_json = json.dumps(
                {
                    "error": "Grading failed unexpectedly. Please try again.",
                    "test_results": [],
                    "student_output": "",
                    "cooldown_seconds": cooldown_seconds,
                    "prediction_feedback": prediction_feedback,
                }
            )
            test_run.status = "done"
            db.session.commit()
        raise
    finally:
        db.session.remove()
