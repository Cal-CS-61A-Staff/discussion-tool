#!/usr/bin/env python3
"""Removes leftover `grader-*` Docker containers left behind by a hard crash
mid-grading (OOM kill, host reboot, `kill -9` on the worker process).

server/services/grading.py already `docker rm -f`s every container it
starts, in a `finally`, for both the normal and timeout paths — so under
ordinary operation nothing should ever be left running. This only exists to
catch the case where the *Python process itself* died before that `finally`
ran, which orphans the container with no owner left to clean it up.

Run periodically, not inline in the app — see deploy/systemd/
cs61a-grader-reaper.{service,timer}.
"""

import os
import subprocess
import sys
from datetime import datetime, timezone

# Generous upper bound on how long a legitimate grading run should ever take
# (server/config.py: GRADER_CONTAINER_TIMEOUT_SECONDS + GRADER_DOCKER_CLI_TIMEOUT_SECONDS,
# plus real slack) — anything still around past this age is orphaned, not slow.
MAX_AGE_SECONDS = int(os.environ.get("GRADER_REAPER_MAX_AGE_SECONDS", 15 + 10 + 60))


def _list_grader_container_ids():
    result = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=grader-", "--format", "{{.ID}}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [cid for cid in result.stdout.split() if cid]


def _started_at(container_id):
    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.StartedAt}}", container_id],
        capture_output=True,
        text=True,
        check=True,
    )
    raw = result.stdout.strip()
    # Docker reports RFC3339Nano, e.g. "2026-08-27T12:00:00.123456789Z" —
    # datetime.fromisoformat wants at most microsecond precision and a
    # "+00:00" offset, not a bare "Z".
    if "." in raw:
        head, _, _ = raw.partition(".")
        raw = f"{head}+00:00"
    else:
        raw = raw.replace("Z", "+00:00")
    return datetime.fromisoformat(raw)


def main():
    removed = []
    for container_id in _list_grader_container_ids():
        try:
            started_at = _started_at(container_id)
        except (subprocess.CalledProcessError, ValueError):
            continue
        age_seconds = (datetime.now(timezone.utc) - started_at).total_seconds()
        if age_seconds > MAX_AGE_SECONDS:
            subprocess.run(["docker", "rm", "-f", container_id], capture_output=True)
            removed.append(container_id)

    if removed:
        print(f"Reaped {len(removed)} orphaned grader container(s): {', '.join(removed)}", file=sys.stderr)


if __name__ == "__main__":
    main()
