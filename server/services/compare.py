import re


def normalize_and_compare(prediction, expected):
    return _normalize(prediction) == _normalize(expected)


def _normalize(text):
    return re.sub(r"\s+", "", text or "")
