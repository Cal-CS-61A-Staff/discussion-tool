"""Compact group-number specs like "1-8,12,15".

Used for Section.assigned_numbers (which rooms cover which group numbers)
and, via that, for seeding a TA's dashboard watch list
(server/blueprints/ta.py). Deliberately forgiving on input (spaces,
trailing commas, reversed ranges) and canonical on output.
"""

_MAX_NUMBER = 999


def parse_number_spec(spec):
    """"1-4, 8,10-9" -> [1, 2, 3, 4, 8, 9, 10]. Sorted, de-duplicated.
    Silently drops anything non-numeric, non-positive, or > _MAX_NUMBER."""
    out = set()
    for chunk in (spec or "").replace(" ", "").split(","):
        if not chunk:
            continue
        if "-" in chunk[1:]:  # a range (leading "-" isn't a valid negative here)
            lo, _, hi = chunk.partition("-")
            try:
                lo, hi = int(lo), int(hi)
            except ValueError:
                continue
            if lo > hi:
                lo, hi = hi, lo
            for n in range(lo, hi + 1):
                if 1 <= n <= _MAX_NUMBER:
                    out.add(n)
        else:
            try:
                n = int(chunk)
            except ValueError:
                continue
            if 1 <= n <= _MAX_NUMBER:
                out.add(n)
    return sorted(out)


def format_number_spec(numbers):
    """[1,2,3,4,8,9,10] -> "1-4,8-10". Inverse of parse_number_spec for the
    canonical form (round-trips)."""
    nums = sorted({int(n) for n in numbers if 1 <= int(n) <= _MAX_NUMBER})
    if not nums:
        return ""
    parts = []
    start = prev = nums[0]
    for n in nums[1:]:
        if n == prev + 1:
            prev = n
            continue
        parts.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = n
    parts.append(str(start) if start == prev else f"{start}-{prev}")
    return ",".join(parts)
