"""Enqueues grading jobs onto the Redis-backed "grading" queue instead of
running Docker inline on a web worker (server/services/grading.py still does
the actual container invocation — only *when* it runs moves, not how).

See server/services/grading_jobs.py for the job body and `flask
grading-worker` (server/app.py) for the process that consumes this queue.
"""

from redis import Redis
from rq import Queue

from server.config import Config

_redis = None
_queue = None


def get_queue():
    global _redis, _queue
    if _queue is None:
        _redis = Redis.from_url(Config.REDIS_URL)
        # A little headroom over the grader's own container/CLI timeouts, so
        # RQ never kills a job that Docker itself was about to time out anyway.
        job_timeout = Config.GRADER_CONTAINER_TIMEOUT_SECONDS + Config.GRADER_DOCKER_CLI_TIMEOUT_SECONDS + 15
        _queue = Queue("grading", connection=_redis, default_timeout=job_timeout)
    return _queue


def enqueue_grading_job(test_run_id, prediction_feedback, cooldown_seconds):
    from server.services.grading_jobs import run_grading_job

    get_queue().enqueue(run_grading_job, test_run_id, prediction_feedback, cooldown_seconds)
