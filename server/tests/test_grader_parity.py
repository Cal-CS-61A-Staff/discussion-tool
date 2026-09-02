"""The TA question editor validates a reference solution in the browser
(client/src/pyodide/authoring.js) against the exact PLTestCase source the
server will later store (server/services/test_case_grading.py). Those two
`generateSimpleTestCode` implementations are hand-kept in sync — this test
fails the build if they drift.

Runs the JS version under node; skipped only when node isn't installed.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from server.services.test_case_grading import generate_simple_test_code

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTHORING_JS = REPO_ROOT / "client" / "src" / "pyodide" / "authoring.js"

# Each entry is one authored {call, expected} set. Covers the escaping
# paths in pyRepr / Python repr: bare identifiers, single vs double
# quotes (and both at once), backslashes, tabs/newlines, unicode, and
# multi-case worksheets. Non-printable control chars are a known gap in
# the JS port and deliberately not exercised here.
FIXTURES = [
    [],
    [{"call": "double(3)", "expected": "6"}],
    [
        {"call": "greet('world')", "expected": "'hello, world'"},
        {"call": "greet('')", "expected": "'hello, '"},
    ],
    [{"call": 'quote("hi")', "expected": 'say "hi"'}],
    [{"call": "apostrophe('x')", "expected": "it's here"}],
    [{"call": "both()", "expected": "he said \"it's\" loudly"}],
    [{"call": "path('a\\\\b')", "expected": "a\\\\b"}],
    [{"call": "lines()", "expected": "line1\nline2\ttabbed"}],
    [{"call": "accented()", "expected": "café résumé"}],
    [
        {"call": "f(1)", "expected": "1"},
        {"call": "f(2)", "expected": "2"},
        {"call": "f(3)", "expected": "3"},
    ],
]

_NODE_DRIVER = """
import { generateSimpleTestCode } from %s;
const chunks = [];
process.stdin.on('data', (c) => chunks.push(c));
process.stdin.on('end', () => {
  const fixtures = JSON.parse(chunks.join(''));
  process.stdout.write(JSON.stringify(fixtures.map((f) => generateSimpleTestCode(f))));
});
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_js_and_python_generate_identical_test_code():
    driver = _NODE_DRIVER % json.dumps(str(AUTHORING_JS))
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", driver],
        input=json.dumps(FIXTURES),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    js_outputs = json.loads(proc.stdout)

    for fixture, js_code in zip(FIXTURES, js_outputs):
        assert js_code == generate_simple_test_code(fixture), f"drift on fixture: {fixture!r}"
