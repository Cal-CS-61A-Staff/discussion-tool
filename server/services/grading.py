"""Orchestrates the sandboxed autograder (grader/ at the repo root).

Each call spins up one ephemeral, resource-limited, network-isolated Docker
container per submission and tears it down unconditionally afterward. This
is deliberately synchronous, one-container-per-call: the correct foundation
for scaling to real concurrency later is putting a job queue in front of
this same invocation, not redesigning it.

Flag combination and the detached-run + `docker wait` (rather than a
foreground run gated by `subprocess.run(timeout=...)`) were both verified
by hand against the built image before being encoded here — a foreground
run whose CLI process gets killed by a Python-side timeout leaves the
container itself running (a real resource leak), so timeouts here always
explicitly `docker rm -f` in a `finally`.
"""

import json
import os
import subprocess
import tempfile
import uuid

from server.config import Config

_DOCKER_RUN_FLAGS = [
    "--network",
    "none",
    "--memory=128m",
    "--cpus=0.5",
    "--pids-limit=64",
    "--cap-drop=ALL",
    "--cap-add=CHOWN",
    "--cap-add=SETUID",
    "--cap-add=SETGID",
    "--security-opt=no-new-privileges",
]


def run_grader(question, code):
    """Run `code` against `question.setup_code`/`question.test_code`.

    Returns a dict shaped like the grader image's JSON result:
    {test_results: [...], total_points, max_points, passed_count,
     total_count, error, student_output}. On any infrastructure failure
    (container wouldn't start, timed out, produced no parseable output)
    returns a synthesized result with `error` set instead of raising —
    this executes untrusted code, so failure is an expected outcome to
    report to the caller, not an exceptional one.
    """
    with tempfile.TemporaryDirectory(prefix="grader-submission-") as tmp_dir:
        _write(tmp_dir, "student_code.py", code)
        _write(tmp_dir, "setup_code.py", question.setup_code or "")
        _write(tmp_dir, "test_code.py", question.test_code or "")

        container_name = f"grader-{uuid.uuid4().hex[:12]}"
        grading_mode = getattr(question, "grading_mode", None) or "pltest"
        try:
            subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    container_name,
                    *_DOCKER_RUN_FLAGS,
                    "-e",
                    f"GRADING_MODE={grading_mode}",
                    "-v",
                    f"{tmp_dir}:/submission:ro",
                    Config.GRADER_IMAGE,
                ],
                capture_output=True,
                text=True,
                timeout=Config.GRADER_DOCKER_CLI_TIMEOUT_SECONDS,
                check=True,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
            return _error_result(f"Could not start the grading sandbox: {e}")

        try:
            return _wait_and_collect(container_name)
        finally:
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                capture_output=True,
                text=True,
                timeout=Config.GRADER_DOCKER_CLI_TIMEOUT_SECONDS,
            )


def _wait_and_collect(container_name):
    try:
        subprocess.run(
            ["docker", "wait", container_name],
            capture_output=True,
            text=True,
            timeout=Config.GRADER_CONTAINER_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return _error_result("Your code timed out (it may have an infinite loop).")

    try:
        logs = subprocess.run(
            ["docker", "logs", container_name],
            capture_output=True,
            text=True,
            timeout=Config.GRADER_DOCKER_CLI_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return _error_result("Timed out reading grading results.")

    try:
        return json.loads(logs.stdout.strip())
    except (ValueError, AttributeError):
        return _error_result("Grading produced no readable output.")


def _write(tmp_dir, filename, content):
    with open(os.path.join(tmp_dir, filename), "w") as f:
        f.write(content)


def _error_result(message):
    return {
        "test_results": [],
        "total_points": 0,
        "max_points": 0,
        "passed_count": 0,
        "total_count": 0,
        "error": message,
        "student_output": "",
    }
