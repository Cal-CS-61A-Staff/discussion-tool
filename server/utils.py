from datetime import datetime, timezone


def utcnow():
    # Naive UTC on purpose: SQLite round-trips DateTime columns as naive
    # values, so every timestamp in this app is naive-UTC to avoid
    # aware/naive comparison errors when a value is re-read from the DB.
    return datetime.now(timezone.utc).replace(tzinfo=None)
