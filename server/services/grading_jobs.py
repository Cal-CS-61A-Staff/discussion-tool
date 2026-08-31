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
from server.services import compare as compare_service
from server.services import grading as grading_service


def run_grading_job(test_run_id, predict_call, student_prediction, cooldown_seconds):
    """Runs the actual sandboxed grader for a pending TestRun and fills in
    its result columns — mirrors the dict shape server/blueprints/groups.py's
    run_tests used to return directly, since GET .../run-tests/:id (the
    polling endpoint) hands results_json straight back to the frontend.

    `predict_call`/`student_prediction` are None when this run has no
    prediction quiz (practice/re-runs — server/blueprints/groups.py:
    practice_run). Otherwise the actual prediction_feedback is only known
    once the sandbox reports what the student's own code did, so it's built
    here, after run_grader returns, rather than upfront.
    """
    try:
        test_run = db.session.get(TestRun, test_run_id)
        if test_run is None:
            return

        question = db.session.get(Question, test_run.question_id)
        results = grading_service.run_grader(question, test_run.code_snapshot, predict_call=predict_call)
        results["cooldown_seconds"] = cooldown_seconds
        results["prediction_feedback"] = compare_service.build_prediction_feedback(
            predict_call, student_prediction, results.pop("predict_result", None)
        )

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
                    # The run itself blew up before the sandbox reported
                    # anything, so there's nothing real to show here.
                    "prediction_feedback": None,
                }
            )
            test_run.status = "done"
            db.session.commit()
        raise
    finally:
        db.session.remove()
