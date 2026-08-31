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


def run_grader(question, code, predict_call=None):
    """Run `code` against `question.setup_code`/`question.test_code`.

    Returns a dict shaped like the grader image's JSON result:
    {test_results: [...], passed_count, total_count, error,
     student_output, predict_result}. On any infrastructure failure
    (container wouldn't start, timed out, produced no parseable output)
    returns a synthesized result with `error` set instead of raising —
    this executes untrusted code, so failure is an expected outcome to
    report to the caller, not an exceptional one.

    `predict_call` (TA/content-authored, never student input) is evaluated
    against the student's own code inside the sandbox — see
    grader/harness/runner.py — so the prediction quiz grades what the
    student's code actually does, not a reference solution.
    """
    with tempfile.TemporaryDirectory(prefix="grader-submission-") as tmp_dir:
        # tempfile.TemporaryDirectory defaults to 0700 (owner-only), which
        # only works if the container's "root" is really host root. Some
        # Docker setups (e.g. userns-remap, rootless) map container root to
        # an unprivileged host UID, which would otherwise get "Permission
        # denied" reading this bind mount even running as root in run.sh.
        # World-readable is fine here: this dir holds only the student's
        # own submitted code, not a secret, and it's gone the moment this
        # `with` block exits.
        os.chmod(tmp_dir, 0o755)
        _write(tmp_dir, "student_code.py", code)
        _write(tmp_dir, "setup_code.py", question.setup_code or "")
        _write(tmp_dir, "test_code.py", question.test_code or "")

        container_name = f"grader-{uuid.uuid4().hex[:12]}"
        grading_mode = getattr(question, "grading_mode", None) or "pltest"
        predict_env = ["-e", f"PL_PREDICT_CALL={predict_call}"] if predict_call else []
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
                    *predict_env,
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
        wait_result = subprocess.run(
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
        # exit code + stderr are the only lead when the container crashed
        # before ever printing its result JSON (e.g. `run.sh`'s `set -e`
        # exiting on a failed setup step) — surfacing them turns a dead-end
        # "no output" into something actually diagnosable instead of
        # guesswork.
        exit_code = wait_result.stdout.strip() if wait_result.stdout else "?"
        detail = logs.stderr.strip() if logs.stderr else ""
        message = f"Grading produced no readable output (container exit code: {exit_code})."
        if detail:
            message += f" stderr: {detail[:500]}"
        return _error_result(message)


def _write(tmp_dir, filename, content):
    path = os.path.join(tmp_dir, filename)
    with open(path, "w") as f:
        f.write(content)
    os.chmod(path, 0o644)


def _error_result(message):
    return {
        "test_results": [],
        "passed_count": 0,
        "total_count": 0,
        "error": message,
        "student_output": "",
    }
