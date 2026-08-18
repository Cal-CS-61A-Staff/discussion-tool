import unittest

from code_feedback import Feedback


class PLTestCase(unittest.TestCase):
    """Base class for question test.py files. `st` is a SimpleNamespace
    exposing everything the student's (setup_code + student_code) execution
    defined at module level, so test methods can call e.g. self.st.tree_sum(...).
    """

    st = None

    def setUp(self):
        self._score = 0.0
        self._messages = []
        Feedback._current = self
