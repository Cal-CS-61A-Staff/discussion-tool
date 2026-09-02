import secrets
from datetime import datetime, timezone


def utcnow():
    # Naive UTC on purpose: SQLite round-trips DateTime columns as naive
    # values, so every timestamp in this app is naive-UTC to avoid
    # aware/naive comparison errors when a value is re-read from the DB.
    return datetime.now(timezone.utc).replace(tzinfo=None)


# Crockford-ish base32 minus the easily-confused characters (I, L, O, U, 0, 1).
_JOIN_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"


def generate_join_code(length=6):
    """A short, unambiguous, human-typable class join code (see
    server/models/klass.py:Class.join_code). Caller is responsible for
    retrying on the (astronomically unlikely) unique-constraint clash."""
    return "".join(secrets.choice(_JOIN_CODE_ALPHABET) for _ in range(length))
