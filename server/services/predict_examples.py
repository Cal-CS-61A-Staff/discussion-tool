"""Extracts {call, expected} pairs a student can be quizzed on before
running their code — one is chosen at random per (group, question) and
persisted on GroupQuestionState.predict_example_json (see
server/blueprints/groups.py:_get_or_create_state) so the whole group is
quizzed on the same call and it doesn't re-randomize on every poll.
"""

import ast
import doctest
import json
import re


def extract_predict_examples_for_question(question):
    """Entry point used by server/blueprints/groups.py. Prefers the
    structured {call, expected} pairs authored via the guided TA form
    (Question.test_cases_json, 'simple' grading mode) when present — no
    parsing needed, they're already in the right shape. Falls back to
    extract_predict_examples for git-authored content (tree worksheet,
    hailstone), unchanged.
    """
    if question.test_cases_json:
        try:
            cases = json.loads(question.test_cases_json)
        except ValueError:
            cases = []
        if cases:
            return [{"call": c["call"], "expected": c["expected"]} for c in cases]

    return extract_predict_examples(question.prompt, question.starter_code, question.expected_output)


def extract_predict_examples(prompt, starter_code, expected_output):
    """Primary path: real >>> examples with shown output, parsed out of the
    student-visible docstrings in starter_code (the hailstone-shaped
    content, where the doctest already has real expected output). Isolated
    to actual docstrings via ast — feeding doctest's parser a whole source
    file (or prompt text mixed with code) makes it swallow trailing
    non-doctest lines as "expected output" for the last example, since it
    has no notion of where a docstring ends.

    Fallback: content whose prompt shows >>> call(s) with no output
    following them (the tree worksheet's prose style) but that does have a
    single expected_output value authored separately — synthesize one
    example from every >>> line in the prompt (in order) plus that value.
    Every line, not just the last: a setup line like `t = Tree(1, ...)`
    ahead of the actual `tree_sum(t)` call has to actually run too, or the
    sandbox evaluating just the last line alone hits a bare NameError.
    """
    examples = _examples_from_docstrings(starter_code)
    if examples:
        return examples

    if expected_output:
        calls = re.findall(r"^>>>\s*(.+)$", prompt or "", re.MULTILINE)
        call = "\n".join(c.strip() for c in calls) if calls else "this code"
        return [{"call": call, "expected": expected_output.strip()}]

    return []


def _examples_from_docstrings(starter_code):
    if not starter_code:
        return []
    try:
        tree = ast.parse(starter_code)
    except SyntaxError:
        return []

    parser = doctest.DocTestParser()
    examples = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        docstring = ast.get_docstring(node)
        if not docstring:
            continue
        try:
            parsed = parser.get_examples(docstring)
        except ValueError:
            continue

        # A docstring's examples share one running REPL session in real
        # doctest semantics — `>>> t = Tree(...)` followed by `>>> tree_sum(t)`
        # is two Examples, but the second only means anything with the
        # first's assignment still in scope. Accumulating every prior line
        # (not just the one with visible `want`) reproduces that: the
        # sandbox (grader/harness/runner.py) actually executes this whole
        # sequence rather than just the last line in isolation.
        accumulated = []
        for ex in parsed:
            accumulated.append(ex.source.rstrip("\n"))
            if ex.want.strip():
                examples.append({"call": "\n".join(accumulated), "expected": ex.want.strip()})
    return examples
