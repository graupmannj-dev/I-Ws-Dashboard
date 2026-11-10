"""Production-compatible GDELT six-root aggregate profile (shadow, v2).

The production discovery engine counts every event with a selected root in
its denominator, even when source actor countries cannot map to a case.
Four-root historical v1, by contrast, counts only mapped cases. NEVER
relabel v1 records as six-root data.
"""
import csv
import datetime as dt
import hashlib
import io
import re
import zipfile
from collections import Counter, defaultdict

ROOT_LABEL = {
    "13": "Threaten", "16": "Reduce relations", "17": "Coerce",
    "18": "Assault", "19": "Fight", "20": "Mass violence",
}
ROOTS = frozenset(ROOT_LABEL)
FOUR_ROOTS = frozenset(("17", "18", "19", "20"))
PROFILE = ("GDELT-v2 EventRootCode 13/16/17/18/19/20, "
           "all-selected-root denominator; production-compatible actor-case assignment")
SCHEMA = "aiba.gdelt.daily.v2"
PREFIX = "aiba/gdelt/roots-13-16-17-18-19-20/v2"


def classify_actors(root, a, b):
    """Exactly match the production v5/v4 case key decision tree."""
    a, b = a.strip(), b.strip()
    valid = lambda c: len(c) == 3 and c.isalpha()
    if valid(a) and valid(b) and a != b:
        return ("BILAT", tuple(sorted((a, b))))
    if root in FOUR_ROOTS and (valid(a) or valid(b)):
        return ("DOMESTIC", (a if valid(a) else b,))
    return None


def case_string(kind_pair):
    if kind_pair is None:
        return None
    return kind_pair[0] + ":" + ":".join(kind_pair[1])


def parse_archive(data, day):
    """Strict schema/CRC validation with no silent malformed-row dropping."""
    if not isinstance(data, bytes):
        raise ValueError("Expected GDELT daily ZIP bytes")
    if not re.fullmatch(r"\d{8}", day):
        raise ValueError("Expected YYYYMMDD")
    target = dt.datetime.strptime(day, "%Y%m%d").date()
    member = f"{day}.export.CSV"
    all_rows, selected, mapped = 0, 0, 0
    counts, root_counts = Counter(), Counter()
    root_case_counts = defaultdict(Counter)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if archive.namelist() != [member]:
                raise ValueError("GDELT daily archive member did not match requested date")
            # CRC verification happens when the stream is fully consumed.
            with archive.open(member) as raw:
                for row in csv.reader(io.TextIOWrapper(raw, encoding="utf-8", errors="strict"), delimiter="\t"):
                    all_rows += 1
                    if len(row) not in (57, 58) or not row[0].isdigit():
                        raise ValueError(f"Malformed GDELT row {all_rows} schema")
                    dt.datetime.strptime(row[1], "%Y%m%d")
                    root = row[28].strip()
                    if (not root.isdigit() and row[26:29] != ["---", "---", "--"]) or row[29] not in ("1", "2", "3", "4"):
                        raise ValueError(f"Malformed GDELT row {all_rows} CAMEO code")
                    if root not in ROOTS:
                        continue
                    selected += 1
                    root_counts[root] += 1
                    case = classify_actors(root, row[7], row[17])
                    if case is None:
                        continue
                    mapped += 1
                    key = case_string(case)
                    counts[key] += 1
                    root_case_counts[key][root] += 1
    except (zipfile.BadZipFile, UnicodeError, EOFError) as exc:
        raise ValueError(f"Invalid GDELT ZIP {day}: {exc}") from exc
    if not all_rows or not selected:
        raise ValueError(f"Empty GDELT source or selected-root denominator on {day}")
    record = {
        "day": day, "rows": all_rows, "selected": selected,
        "mapped": mapped, "unmapped": selected - mapped,
        "counts": dict(sorted(counts.items())),
        "root_selected_counts": dict(sorted(root_counts.items())),
        "root_case_counts": {key: dict(sorted(roots.items()))
                             for key, roots in sorted(root_case_counts.items())},
        "profile": PROFILE, "schema": SCHEMA,
        "zip_sha256": hashlib.sha256(data).hexdigest(),
    }
    validate(record, target)
    return record


def validate(record, expected_day=None):
    if record.get("schema") != SCHEMA or record.get("profile") != PROFILE:
        raise ValueError("Six-root schema/profile mismatch")
    day = dt.datetime.strptime(record["day"], "%Y%m%d").date()
    if expected_day and day != expected_day:
        raise ValueError("Six-root daily date mismatch")
    counts = record["counts"]
    roots = record["root_selected_counts"]
    by_case = record["root_case_counts"]
    if not isinstance(record["rows"], int) or record["rows"] < record["selected"]:
        raise ValueError("Invalid full-source row count")
    if not isinstance(record["selected"], int) or record["selected"] <= 0:
        raise ValueError("Invalid six-root denominator")
    if set(roots) - ROOTS or sum(roots.values()) != record["selected"]:
        raise ValueError("Root category denominator mismatch")
    if sum(counts.values()) != record["mapped"] or record["unmapped"] != record["selected"] - record["mapped"]:
        raise ValueError("Mapped source denominator mismatch")
    if not (0 <= record["mapped"] <= record["selected"]):
        raise ValueError("Invalid mapped count")
    if set(counts) != set(by_case) or any(
        sum(by_case[k].values()) != v or set(by_case[k]) - ROOTS for k, v in counts.items()
    ):
        raise ValueError("Case-by-root counts inconsistent")
    if any(type(x) is not int or x < 0 for x in [*counts.values(), *roots.values()]
           + [z for vs in by_case.values() for z in vs.values()]):
        raise ValueError("Negative or non-integer source counts")
    if not re.fullmatch(r"[a-f0-9]{64}", record["zip_sha256"]):
        raise ValueError("Missing SHA-256 archive provenance")
    return day


def four_root_projection(record):
    """Exactly the counts that should match already-persisted 17–20 v1."""
    validate(record)
    mapped = {
        key: sum(v for r, v in roots.items() if r in FOUR_ROOTS)
        for key, roots in record["root_case_counts"].items()
    }
    mapped = {k: v for k, v in mapped.items() if v}
    return {"day": record["day"], "rows": record["rows"],
            "selected": sum(mapped.values()), "counts": mapped}


def crosscheck_v1(record_v2, record_v1):
    four = four_root_projection(record_v2)
    for field in ("day", "rows", "selected", "counts"):
        if four[field] != record_v1[field]:
            raise ValueError(f"GDELT 17–20 parity check failed: {field} differs; do not write v2")
    return True
