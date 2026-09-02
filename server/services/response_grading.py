"""Authoring schema, auto-checking, and answer-stripping for non-code
question types (Question.problem_type != 'coding').

`content_json` on the question holds the type-specific config:

  multiple_choice     {"options": [{"text": str, "correct": bool}, ...],
                       "multiple": bool}
  dropdown            {"options": [{"text": str, "correct": bool}, ...]}
  fill_blank_code     {"template": str with [[1]] [[2]] markers,
  fill_blank_markdown  "blanks": [{"answer": str, "accept": [str],
                                   "case_sensitive": bool}, ...]}
  short_answer        {"answer": str, "accept": [str], "case_sensitive": bool}
                       -- empty answer + no accept => ungraded prompt
  text_markdown       {}                      (prompt is the content)
  plain_text          {"min_length": int}     (free response, stored, never checked)
  image               {"url": str, "alt": str, "max_width": int}
  iframe              {"url": str, "height": int}
  counterexample      {"params": [{"name": str}], "call": str,
                       "buggy_code": str, "reference_code": str,
                       "constraints": str, "setup": str}
                       -- student supplies input values; graded by running
                          buggy vs reference in the sandbox on submit
                          (server/blueprints/groups.py) -- correct if the
                          outputs differ or the buggy code times out.

The optional prediction prompt (Question.prediction_json, ANY problem_type):
  output   {"mode": "output", "setup": str, "calls": [str],
            "items": [{"code", "expected"}]}
           -- `calls` are call expressions (e.g. fizzbuzz(5)); each is run
              against the question's own code at save time
              (server/blueprints/admin.py:_resolve_prediction_items) and
              the output stored as `expected`. One item is drawn per group.
  written  {"mode": "written", "prompt": str}
`validate_prediction` here cleans it; `items` is filled in at save time.

The student's stored `response_json` shape by type:
  choice types        list[int]   selected option indices
  fill blank types    list[str]   one string per blank, in order
  short_answer        str
  plain_text          str
  counterexample      {param_name: str, ...}   one literal per input
"""

import json
import re

CHOICE_TYPES = {"multiple_choice", "dropdown"}
FILL_BLANK_TYPES = {"fill_blank_code", "fill_blank_markdown"}
DISPLAY_TYPES = {"text_markdown", "image", "iframe", "plain_text"}
# counterexample is auto-checkable but graded out-of-band (needs the sandbox),
# so check_response returns None for it and the endpoint stores is_correct.
GRADEABLE_TYPES = CHOICE_TYPES | FILL_BLANK_TYPES | {"short_answer", "counterexample"}
NONCODE_TYPES = GRADEABLE_TYPES | DISPLAY_TYPES
ALL_PROBLEM_TYPES = {"coding"} | NONCODE_TYPES

BLANK_MARKER = re.compile(r"\[\[(\d+)\]\]")


def validate_prediction(pred):
    """The optional prediction prompt, on any problem_type. Returns
    (clean_dict, None) or (None, error). NULL/empty -> (None, None).

    'output' mode is a list of call expressions (one per line), e.g.
    `fizzbuzz(5)`. The TA editor runs each against the question's code in
    the browser (Pyodide) and sends the captured outputs back as `items`
    (list of {code, expected}); here we just shape-check them.
    """
    if not pred or not isinstance(pred, dict):
        return None, None
    mode = pred.get("mode") or "output"
    if mode not in ("output", "written"):
        return None, "prediction mode must be 'output' or 'written'"
    if mode == "written":
        prompt = (pred.get("prompt") or "").strip()
        if not prompt:
            return None, "a written prediction needs a prompt"
        return {"mode": "written", "prompt": prompt}, None

    calls = [ln.strip() for ln in (pred.get("calls") or "").splitlines()] if isinstance(pred.get("calls"), str) else [
        str(c).strip() for c in (pred.get("calls") or [])
    ]
    calls = [c for c in calls if c]
    if not calls:
        return None, "add at least one call to predict, e.g. fizzbuzz(5)"
    items = []
    for it in pred.get("items") or []:
        if isinstance(it, dict) and it.get("code"):
            items.append({"code": str(it["code"]), "expected": str(it.get("expected", ""))})
    if len(items) != len(calls):
        return None, "prediction items weren't resolved — try saving again once Python has loaded"
    return {"mode": "output", "setup": pred.get("setup") or "", "calls": calls, "items": items}, None


def parse_content(question):
    """content_json -> dict, tolerant of NULL / malformed."""
    raw = getattr(question, "content_json", None)
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _norm(text, case_sensitive):
    text = (text or "").strip()
    return text if case_sensitive else text.lower()


def _correct_index_set(content):
    return {i for i, opt in enumerate(content.get("options", []) or []) if opt.get("correct")}


def _as_index_set(response):
    out = set()
    items = response if isinstance(response, (list, tuple)) else [response]
    for item in items:
        if isinstance(item, bool):
            continue
        if isinstance(item, int):
            out.add(item)
        elif isinstance(item, str) and item.strip().lstrip("-").isdigit():
            out.add(int(item.strip()))
    return out


def is_auto_checkable(question):
    """True when a submitted answer can be marked right/wrong (so a correct
    group answer gates advancing). A short_answer with no model answer is a
    prompt, not a graded question. 'counterexample' is checked in the
    sandbox by the submit endpoint, not here."""
    ptype = getattr(question, "problem_type", "coding")
    if ptype in CHOICE_TYPES or ptype in FILL_BLANK_TYPES or ptype == "counterexample":
        return True
    if ptype == "short_answer":
        content = parse_content(question)
        return bool((content.get("answer") or "").strip() or content.get("accept"))
    return False


def normalize_output(text):
    """Loose match for predicted vs actual program output — ignore
    leading/trailing whitespace on each line and blank lines at the ends
    (a student shouldn't fail for a stray leading space)."""
    lines = [ln.strip() for ln in str(text or "").splitlines()]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def check_prediction(expected, response):
    return normalize_output(response) == normalize_output(expected)


def check_response(question, response):
    """Returns True/False for auto-checkable questions, or None when the
    type isn't graded in-process (display types, ungraded short_answer /
    plain_text, and 'counterexample' which the endpoint grades via the
    sandbox)."""
    ptype = getattr(question, "problem_type", "coding")
    if not is_auto_checkable(question) or ptype == "counterexample":
        return None
    content = parse_content(question)

    if ptype in CHOICE_TYPES:
        return _as_index_set(response) == _correct_index_set(content)

    if ptype in FILL_BLANK_TYPES:
        blanks = content.get("blanks") or []
        given = response if isinstance(response, (list, tuple)) else [response]
        if len(given) != len(blanks):
            return False
        for value, blank in zip(given, blanks):
            cs = bool(blank.get("case_sensitive"))
            accepted = {_norm(blank.get("answer"), cs)}
            accepted.update(_norm(a, cs) for a in (blank.get("accept") or []))
            accepted.discard("")
            if _norm(value if isinstance(value, str) else "", cs) not in accepted:
                return False
        return True

    # short_answer
    cs = bool(content.get("case_sensitive"))
    accepted = {_norm(content.get("answer"), cs)}
    accepted.update(_norm(a, cs) for a in (content.get("accept") or []))
    accepted.discard("")
    return _norm(response if isinstance(response, str) else "", cs) in accepted


def public_content(question):
    """The content dict with every answer-revealing key removed — safe to
    send to students in the /state payload."""
    ptype = getattr(question, "problem_type", "coding")
    if ptype == "coding":
        return None
    content = parse_content(question)

    if ptype in CHOICE_TYPES:
        options = [{"text": opt.get("text", "")} for opt in (content.get("options") or [])]
        out = {"options": options}
        if ptype == "multiple_choice":
            out["multiple"] = bool(content.get("multiple"))
        return out

    if ptype in FILL_BLANK_TYPES:
        return {
            "template": content.get("template", ""),
            "blank_count": len(content.get("blanks") or []),
        }

    if ptype == "short_answer":
        return {"graded": is_auto_checkable(question)}

    if ptype == "plain_text":
        return {"min_length": int(content.get("min_length") or 0)}

    if ptype == "image":
        return {
            "url": content.get("url", ""),
            "alt": content.get("alt", ""),
            "max_width": content.get("max_width") or None,
        }

    if ptype == "iframe":
        return {"url": content.get("url", ""), "height": content.get("height") or 400}

    if ptype == "counterexample":
        # reference_code + setup are needed client-side now that grading
        # runs in the browser (Pyodide). This does reveal a correct
        # implementation to a student who digs into the network payload,
        # which is an accepted trade for a participation-graded exercise
        # whose task is "find a breaking input", not "write the solution".
        return {
            "params": content.get("params") or [],
            "call": content.get("call", ""),
            "buggy_code": content.get("buggy_code", ""),
            "reference_code": content.get("reference_code", ""),
            "setup": content.get("setup", ""),
            "constraints": content.get("constraints", ""),
        }

    return {}  # text_markdown


def validate_content(problem_type, content):
    """Authoring-time validation. Returns (clean_content_dict, None) or
    (None, error_message)."""
    if not isinstance(content, dict):
        return None, "content must be an object"

    if problem_type in CHOICE_TYPES:
        raw_options = content.get("options") or []
        options = []
        for opt in raw_options:
            text = (opt.get("text") or "").strip() if isinstance(opt, dict) else ""
            if text:
                options.append({"text": text, "correct": bool(isinstance(opt, dict) and opt.get("correct"))})
        if len(options) < 2:
            return None, "at least two answer options are required"
        correct_count = sum(1 for o in options if o["correct"])
        if correct_count < 1:
            return None, "mark at least one option correct"
        if problem_type == "dropdown" and correct_count != 1:
            return None, "a dropdown must have exactly one correct option"
        clean = {"options": options}
        if problem_type == "multiple_choice":
            clean["multiple"] = bool(content.get("multiple")) or correct_count > 1
        return clean, None

    if problem_type in FILL_BLANK_TYPES:
        template = (content.get("template") or "").strip()
        if not template:
            return None, "a template with [[1]] blank markers is required"
        markers = sorted({int(n) for n in BLANK_MARKER.findall(template)})
        if not markers:
            return None, "the template needs at least one [[1]] blank marker"
        if markers != list(range(1, len(markers) + 1)):
            return None, "blank markers must be numbered 1..N with no gaps"
        raw_blanks = content.get("blanks") or []
        if len(raw_blanks) != len(markers):
            return None, f"expected {len(markers)} blank answer(s), got {len(raw_blanks)}"
        blanks = []
        for i, blank in enumerate(raw_blanks, start=1):
            answer = (blank.get("answer") or "").strip() if isinstance(blank, dict) else ""
            if not answer:
                return None, f"blank {i} needs an answer"
            accept = [a.strip() for a in (blank.get("accept") or []) if isinstance(a, str) and a.strip()]
            blanks.append(
                {
                    "answer": answer,
                    "accept": accept,
                    "case_sensitive": bool(isinstance(blank, dict) and blank.get("case_sensitive")),
                }
            )
        return {"template": template, "blanks": blanks}, None

    if problem_type == "short_answer":
        answer = (content.get("answer") or "").strip()
        accept = [a.strip() for a in (content.get("accept") or []) if isinstance(a, str) and a.strip()]
        return {
            "answer": answer,
            "accept": accept,
            "case_sensitive": bool(content.get("case_sensitive")),
        }, None

    if problem_type == "plain_text":
        try:
            min_length = max(0, int(content.get("min_length") or 0))
        except (TypeError, ValueError):
            min_length = 0
        return {"min_length": min_length}, None

    if problem_type == "text_markdown":
        return {}, None

    if problem_type == "image":
        url = (content.get("url") or "").strip()
        if not url:
            return None, "an image URL is required"
        clean = {"url": url, "alt": (content.get("alt") or "").strip()}
        try:
            if content.get("max_width"):
                clean["max_width"] = int(content["max_width"])
        except (TypeError, ValueError):
            pass
        return clean, None

    if problem_type == "iframe":
        url = (content.get("url") or "").strip()
        if not url:
            return None, "an embed URL is required"
        try:
            height = int(content.get("height") or 400)
        except (TypeError, ValueError):
            height = 400
        return {"url": url, "height": max(100, height)}, None

    if problem_type == "counterexample":
        import ast

        params = []
        for p in content.get("params") or []:
            name = (p.get("name") or "").strip() if isinstance(p, dict) else str(p).strip()
            if name.isidentifier():
                params.append({"name": name})
        if not params:
            return None, "at least one input parameter is required"
        call = (content.get("call") or "").strip()
        if not call:
            return None, "a call template (e.g. race(x, y)) is required"
        for key in ("buggy_code", "reference_code"):
            src = content.get(key) or ""
            if not src.strip():
                return None, f"{key.replace('_', ' ')} is required"
            try:
                ast.parse(src)
            except SyntaxError as exc:
                return None, f"{key.replace('_', ' ')} has a syntax error: {exc}"
        return {
            "params": params,
            "call": call,
            "buggy_code": content["buggy_code"],
            "reference_code": content["reference_code"],
            "constraints": (content.get("constraints") or "").strip(),
            "setup": content.get("setup") or "",
        }, None

    return None, f"unknown problem_type: {problem_type}"
