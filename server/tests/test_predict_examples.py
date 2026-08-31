from server.services.predict_examples import extract_predict_examples

HAILSTONE_STARTER = '''def hailstone(n):
    """Print the hailstone sequence starting at n and return its number of steps.

    >>> a = hailstone(10)
    10
    5
    16
    8
    4
    2
    1
    >>> a
    7
    >>> b = hailstone(1)
    1
    >>> b
    1
    """
    pass
'''

TREE_PROMPT = (
    "Trace tree_sum(t), which returns the sum of all labels in t.\n\n"
    ">>> t = Tree(1, [Tree(2), Tree(3)])\n>>> tree_sum(t)"
)
TREE_STARTER = "def tree_sum(t):\n    return t.label + sum([tree_sum(b) for b in t.branches])"


def test_extracts_real_doctest_examples_from_docstring():
    examples = extract_predict_examples("some prompt text", HAILSTONE_STARTER, None)

    assert len(examples) == 4
    # A docstring's examples share one running session in real doctest
    # semantics -- `a` alone (examples[1]) only means anything with the
    # `a = hailstone(10)` assignment still in scope, so the call has to
    # include it too, not just the line that actually shows output.
    assert examples[0] == {"call": "a = hailstone(10)", "expected": "10\n5\n16\n8\n4\n2\n1"}
    assert examples[1] == {"call": "a = hailstone(10)\na", "expected": "7"}
    # the last example must not swallow anything past the docstring (the
    # closing """ / trailing `pass`) into its expected output
    assert examples[3] == {"call": "a = hailstone(10)\na\nb = hailstone(1)\nb", "expected": "1"}


def test_falls_back_to_expected_output_when_prompt_has_no_shown_output():
    examples = extract_predict_examples(TREE_PROMPT, TREE_STARTER, "6")

    # Both >>> lines, not just the last -- `tree_sum(t)` alone would hit a
    # bare NameError in the sandbox without `t = Tree(...)` run first.
    assert examples == [{"call": "t = Tree(1, [Tree(2), Tree(3)])\ntree_sum(t)", "expected": "6"}]


def test_returns_empty_when_neither_source_is_usable():
    assert extract_predict_examples("no examples here", "def f(): pass", None) == []


def test_ignores_examples_with_no_shown_output():
    starter = '''def f(x):
    """
    >>> y = f(1)
    """
    pass
'''
    # `y = f(1)` prints nothing and has no want — nothing to quiz on, and no
    # expected_output fallback either, so this should yield no examples.
    assert extract_predict_examples("", starter, None) == []
