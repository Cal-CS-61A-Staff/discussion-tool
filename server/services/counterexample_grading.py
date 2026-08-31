"""Synchronous sandbox grading for 'counterexample' questions.

The student supplies input values; we run the buggy code and a correct
reference the TA authored with those inputs in the grader sandbox and
decide whether the student found a case where the two disagree (or the
buggy one loops forever / raises where the reference doesn't).
"""

import ast
from types import SimpleNamespace

from server.services import grading as grading_service
from server.services import response_grading


def _literals(params, values):
    out = {}
    for name in params:
        raw = (values or {}).get(name, "")
        try:
            out[name] = ast.literal_eval(str(raw))
        except (ValueError, SyntaxError, TypeError):
            return None, f"input '{name}' must be a plain number, string, or tuple"
    return out, None


def _run(code, setup, predict_call):
    # 'doctest' mode just loads the module and evaluates PL_PREDICT_CALL
    # against it (no docstrings needed) — see grader/harness/runner.py.
    fake = SimpleNamespace(setup_code=setup or "", test_code="", grading_mode="doctest")
    return grading_service.run_grader(fake, code, predict_call=predict_call)


def grade(question, values):
    """Returns (is_correct: bool | None, error: str | None). A non-None
    `error` means reject the submission with a 4xx (bad input, constraint
    not met, or an infrastructure failure) rather than marking it wrong.
    """
    content = response_grading.parse_content(question)
    params = [p["name"] for p in content.get("params") or []]

    literals, err = _literals(params, values)
    if err:
        return None, err

    constraints = (content.get("constraints") or "").strip()
    if constraints:
        try:
            if not eval(constraints, {"__builtins__": {}}, dict(literals)):  # noqa: S307 - TA-authored, builtins stripped
                return None, "those inputs don't satisfy the stated constraints"
        except Exception:  # noqa: BLE001 - a broken constraint shouldn't block the student
            pass

    predict_call = (
        "\n".join(f"{name} = {literals[name]!r}" for name in params) + "\n" + content.get("call", "")
    )
    setup = content.get("setup", "")
    buggy = _run(content.get("buggy_code", ""), setup, predict_call)
    reference = _run(content.get("reference_code", ""), setup, predict_call)

    if "timed out" in (buggy.get("error") or "").lower():
        return True, None  # the buggy code loops forever on these inputs
    if buggy.get("error"):
        return None, "couldn't run the code with those inputs — check the format"
    if reference.get("error"):
        return None, "couldn't run the reference solution — tell your TA"

    b, r = buggy.get("predict_result"), reference.get("predict_result")
    if not b or not r:
        return None, "the grader didn't return a result — try again"
    if b.get("kind") == "error" and r.get("kind") != "error":
        return True, None  # buggy raises where the correct one doesn't
    if b.get("kind") == "value" and r.get("kind") == "value":
        differ = response_grading.normalize_output(b.get("repr")) != response_grading.normalize_output(r.get("repr"))
        return differ, None
    return b != r, None
