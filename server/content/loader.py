"""Loads worksheets authored as markdown directories (content/worksheets/).

This is today's implementation of a "content source" — the abstraction
boundary mirrors server/auth.py: load_worksheet_from_dir reads local files
now, and a future load_worksheet_from_repo(url) could fetch the same shape
from an external repo later without server/seed.py or anything downstream
needing to change.

Question markdown format:

    id: hailstone
    title: Hailstone
    code: hailstone.py
    ---

    <markdown prose, may include>

    @code hailstone.py          # not rendered — pulls in the sibling file as starter_code
    @pytest hailstone           # not rendered — grade via doctests in the student's own code
    :::solution
    <markdown, extracted into solution_markdown, not part of the displayed prompt>
    :::
"""

import json
import re
from pathlib import Path

_KV_LINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$")
_SOLUTION_RE = re.compile(r":::solution\s*\n(.*?)\n:::", re.DOTALL)
_CODE_DIRECTIVE_RE = re.compile(r"^@code\s+(\S+)\s*$", re.MULTILINE)
_PYTEST_DIRECTIVE_RE = re.compile(r"^@pytest\s+(\S+)\s*$", re.MULTILINE)


def discover_worksheet_dirs(content_root):
    """Returns every directory under content_root/worksheets/ that has a manifest.json."""
    worksheets_dir = Path(content_root) / "worksheets"
    if not worksheets_dir.exists():
        return []
    return sorted(p.parent for p in worksheets_dir.glob("*/manifest.json"))


def load_worksheet_from_dir(worksheet_dir):
    """Returns the same shape server/seed.py already expects from the JSON
    fixtures: {slug, title, description, class_course_name, class_name,
    questions: [...]}. class_course_name/class_name declare which class
    (Section) this assignment belongs to — seed.py upserts the class first,
    then the worksheet under it, so multiple assignments can share one class.
    """
    worksheet_dir = Path(worksheet_dir)
    with open(worksheet_dir / "manifest.json") as f:
        manifest = json.load(f)

    questions = []
    for order_index, question_id in enumerate(manifest["question_ids"]):
        question_path = worksheet_dir / "questions" / question_id / "question.md"
        parsed = parse_question_markdown(question_path)
        parsed["order_index"] = order_index
        questions.append(parsed)

    return {
        "slug": manifest["slug"],
        "title": manifest["title"],
        "description": manifest.get("description", ""),
        "class_course_name": manifest["class_course_name"],
        "class_name": manifest["class_name"],
        "questions": questions,
    }


def parse_question_markdown(path):
    path = Path(path)
    question_dir = path.parent
    frontmatter, body = _split_frontmatter(path.read_text())

    solution_markdown = None
    solution_match = _SOLUTION_RE.search(body)
    if solution_match:
        solution_markdown = solution_match.group(1).strip()
        body = body[: solution_match.start()] + body[solution_match.end() :]

    starter_code = ""
    code_match = _CODE_DIRECTIVE_RE.search(body)
    if code_match:
        starter_code = (question_dir / code_match.group(1)).read_text()
        body = _CODE_DIRECTIVE_RE.sub("", body, count=1)

    grading_mode = "pltest"
    pytest_match = _PYTEST_DIRECTIVE_RE.search(body)
    if pytest_match:
        grading_mode = "doctest"
        pytest_name = pytest_match.group(1)
        question_id = frontmatter.get("id")
        if question_id and pytest_name != question_id:
            print(f"warning: @pytest {pytest_name} != id {question_id} in {path}")
        body = _PYTEST_DIRECTIVE_RE.sub("", body, count=1)

    return {
        "id": frontmatter.get("id"),
        "title": frontmatter.get("title", frontmatter.get("id", "")),
        "prompt": _collapse_blank_lines(body).strip(),
        "starter_code": starter_code,
        "expected_output": None,
        "language": "python",
        "setup_code": "",
        "test_code": "",
        "grading_mode": grading_mode,
        # git-authored content is code-only for now; non-code problem types
        # are created through the guided TA form.
        "problem_type": frontmatter.get("type", "coding"),
        "content_json": None,
        "solution_markdown": solution_markdown,
    }


def _split_frontmatter(text):
    lines = text.split("\n")
    start = 1 if lines and lines[0].strip() == "---" else 0

    frontmatter = {}
    i = start
    while i < len(lines):
        line = lines[i]
        if line.strip() == "---":
            i += 1
            break
        match = _KV_LINE_RE.match(line)
        if not match:
            break
        frontmatter[match.group(1).strip()] = match.group(2).strip()
        i += 1

    return frontmatter, "\n".join(lines[i:])


def _collapse_blank_lines(text):
    return re.sub(r"\n{3,}", "\n\n", text)
