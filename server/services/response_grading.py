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
  prediction          {"setup": str, "doctest": str,      -- raw TA input
                        "items": [{"code": str, "expected": str}, ...]}
                       -- items parsed from `doctest` on save and verified
                          in the sandbox; one is drawn at random per group
                          (GroupQuestionState.predict_example_json holds the
                          chosen index) and the student predicts its output.

The student's stored `response_json` shape by type:
  choice types        list[int]   selected option indices
  fill blank types    list[str]   one string per blank, in order
  short_answer        str
  plain_text          str
  prediction          str         the predicted program output
"""

import doctest
import json
import re

CHOICE_TYPES = {"multiple_choice", "dropdown"}
FILL_BLANK_TYPES = {"fill_blank_code", "fill_blank_markdown"}
DISPLAY_TYPES = {"text_markdown", "image", "iframe", "plain_text"}
GRADEABLE_TYPES = CHOICE_TYPES | FILL_BLANK_TYPES | {"short_answer", "prediction"}
NONCODE_TYPES = GRADEABLE_TYPES | DISPLAY_TYPES
ALL_PROBLEM_TYPES = {"coding"} | NONCODE_TYPES

BLANK_MARKER = re.compile(r"\[\[(\d+)\]\]")


def parse_prediction_items(doctest_text):
    """A block of >>> examples -> [{"code", "expected"}]. Mirrors
    server/services/predict_examples.py:_examples_from_docstrings — a run
    of >>> lines shares one REPL session, so each emitted item carries
    every preceding source line (setup assignments etc.) plus the line
    whose output is shown. Returns (items, error_message_or_None).
    """
    try:
        examples = doctest.DocTestParser().get_examples(doctest_text or "")
    except ValueError as exc:
        return None, f"couldn't parse the >>> examples: {exc}"

    items = []
    accumulated = []
    for ex in examples:
        accumulated.append(ex.source.rstrip("\n"))
        if ex.want.strip():
            items.append({"code": "\n".join(accumulated), "expected": ex.want.rstrip("\n")})
            accumulated = []  # each item is independent — don't carry lines forward
    if not items:
        return None, "add at least one >>> example with its expected output on the next line"
    return items, None


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
    """True when a submitted answer can be marked right/wrong in-process
    (so a correct group answer gates advancing). A short_answer with no
    model answer is a prompt, not a graded question."""
    ptype = getattr(question, "problem_type", "coding")
    if ptype in CHOICE_TYPES or ptype in FILL_BLANK_TYPES or ptype == "prediction":
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


def check_response(question, response, *, prediction_expected=None):
    """Returns True/False for auto-checkable questions, or None when the
    type isn't graded (display types, ungraded short_answer/plain_text).
    `prediction_expected` is the drawn item's verified output — the caller
    resolves it from the group's GroupQuestionState."""
    ptype = getattr(question, "problem_type", "coding")
    if not is_auto_checkable(question):
        return None
    if ptype == "prediction":
        if prediction_expected is None:
            return None
        return check_prediction(prediction_expected, response)
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

    if ptype == "prediction":
        # The chosen item's code is spliced in per-group by the serializer
        # (it needs GroupQuestionState); here we only expose the shared
        # setup and the item count. Never the expected outputs.
        return {"setup": content.get("setup", ""), "item_count": len(content.get("items") or [])}

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

    if problem_type == "prediction":
        setup = content.get("setup") or ""
        doctest_text = content.get("doctest") or ""
        items, err = parse_prediction_items(doctest_text)
        if err:
            return None, err
        # The parsed `expected` values are re-verified against the sandbox
        # by server/blueprints/admin.py before the save is accepted.
        return {"setup": setup, "doctest": doctest_text, "items": items}, None

    return None, f"unknown problem_type: {problem_type}"
