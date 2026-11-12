#!/usr/bin/env python3
"""Local append-only AIBA tipper evidence ledger (experimental, no alert promotion).

An SHA-256 chain detects accidental edits/reordering but does NOT establish
trusted time or prevent a privileged operator replacing the entire file.
Append timestamps come from this machine's UTC clock; no caller-provided
issuance timestamp is accepted. Anchor externally before claims of immutability.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

SCHEMA = "aiba.tipper-ledger-entry.v1"
GENESIS = "0" * 64
MAX_LEDGER_BYTES = 8 * 1024 * 1024
MAX_LINE_BYTES = 64 * 1024
MAX_ENTRIES = 6000
MAX_PAYLOAD_BYTES = 48 * 1024
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{1,63}\Z")
COUNTRY_RE = re.compile(r"[A-Z]{2}\Z")
UTC_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")


class LedgerError(ValueError):
    pass


def iso_time(value):
    if not isinstance(value, str) or not UTC_RE.fullmatch(value):
        raise LedgerError("timestamps_must_be_UTC_seconds_Z")
    try:
        moment = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise LedgerError("invalid_utc_timestamp") from exc
    return moment.replace(tzinfo=dt.timezone.utc)


def utc_now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def clean_string(value, label, *, minimum=3, maximum=500):
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        raise LedgerError("missing_or_invalid_" + label)
    if any(ord(c) < 32 for c in value):
        raise LedgerError("control_character_in_" + label)
    return value.strip()


def clean_id(value, label):
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise LedgerError("invalid_" + label)
    return value


def object_unique(pairs):
    value = {}
    for k, v in pairs:
        if k in value:
            raise LedgerError("duplicate_json_key")
        value[k] = v
    return value


def json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def load_json_file(path):
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_PAYLOAD_BYTES:
        raise LedgerError("missing_or_oversized_payload")
    try:
        return json.loads(path.read_bytes(), object_pairs_hook=object_unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(LedgerError("nonfinite_json")))
    except (UnicodeError, ValueError, RecursionError, OSError) as exc:
        raise LedgerError("invalid_payload_json") from exc


def validate_issuance(p, timestamp):
    required = {"tipper_id", "actors", "action_key", "country", "location_note",
                "consequence", "horizon_end", "confidence", "evidence",
                "counter_indicators", "alternatives", "analyst_action", "issuer"}
    if not isinstance(p, dict) or set(p) != required:
        raise LedgerError("issuance_fields_mismatch")
    clean_id(p["tipper_id"], "tipper_id")
    clean_id(p["issuer"], "issuer")
    if not isinstance(p["actors"], list) or not 1 <= len(p["actors"]) <= 8:
        raise LedgerError("invalid_forecast_actors")
    actors = [clean_string(a, "actor", maximum=100) for a in p["actors"]]
    if len(set(actors)) != len(actors):
        raise LedgerError("duplicate_forecast_actor")
    clean_string(p["action_key"], "action_key", maximum=160)
    if not isinstance(p["country"], str) or not COUNTRY_RE.fullmatch(p["country"]):
        raise LedgerError("invalid_country_code")
    for name in ("location_note", "consequence", "analyst_action"):
        clean_string(p[name], name)
    now = iso_time(timestamp)
    horizon = iso_time(p["horizon_end"])
    if not now < horizon <= now + dt.timedelta(days=90):
        raise LedgerError("forecast_horizon_must_be_future_and_bounded")
    confidence = p["confidence"]
    if (type(confidence) not in (int, float) or not 0 < confidence < 1):
        raise LedgerError("confidence_must_be_uncalibrated_0_to_1")
    for field in ("counter_indicators", "alternatives"):
        values = p[field]
        if not isinstance(values, list) or len(values) > 15:
            raise LedgerError("invalid_" + field)
        for value in values:
            clean_string(value, field)
    evidence = p["evidence"]
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= 16:
        raise LedgerError("missing_bounded_preissuance_evidence")
    seen = set()
    for entry in evidence:
        keys = {"family", "original_provider", "source_id", "observed_at",
                "available_at", "collected_at", "quality"}
        if not isinstance(entry, dict) or set(entry) != keys:
            raise LedgerError("invalid_source_evidence_schema")
        for name in ("family", "original_provider", "source_id"):
            clean_string(entry[name], name, maximum=300)
        if entry["quality"] not in ("complete", "partial", "unknown"):
            raise LedgerError("invalid_evidence_quality")
        observed, available, collected = (iso_time(entry[k]) for k in (
            "observed_at", "available_at", "collected_at"))
        if not observed <= available <= collected <= now:
            raise LedgerError("evidence_not_available_as_of_issuance")
        source_key = (entry["original_provider"], entry["source_id"])
        if source_key in seen:
            raise LedgerError("duplicate_underlying_evidence")
        seen.add(source_key)


def validate_report(p, recorded):
    keys = {"tipper_id", "kind", "event_time", "source_ref", "reviewer",
            "publication_scope_reviewed"}
    if not isinstance(p, dict) or set(p) != keys:
        raise LedgerError("report_fields_mismatch")
    clean_id(p["tipper_id"], "tipper_id")
    clean_id(p["reviewer"], "report_reviewer")
    clean_string(p["source_ref"], "news_source_ref", maximum=700)
    if p["kind"] not in ("credible_publication", "gdelt_first_seen"):
        raise LedgerError("invalid_report_kind")
    if type(p["publication_scope_reviewed"]) is not bool:
        raise LedgerError("invalid_publication_review_state")
    if p["kind"] == "gdelt_first_seen" and p["publication_scope_reviewed"]:
        raise LedgerError("gdelt_not_credible_first_publication")
    if iso_time(p["event_time"]) > iso_time(recorded):
        raise LedgerError("report_timestamp_in_future")


def validate_adjudication(p, recorded, issued):
    keys = {"tipper_id", "outcome", "case_id", "reviewer", "source_ref",
            "adjudication_note", "event_time", "actors_match", "action_match",
            "geography_match", "verified_through", "coverage_complete", "revision_reason"}
    if not isinstance(p, dict) or set(p) != keys:
        raise LedgerError("adjudication_fields_mismatch")
    clean_id(p["tipper_id"], "tipper_id")
    clean_id(p["case_id"], "case_id")
    clean_id(p["reviewer"], "reviewer")
    clean_string(p["source_ref"], "adjudication_source_ref", maximum=700)
    clean_string(p["adjudication_note"], "adjudication_note", minimum=20, maximum=1200)
    if p["outcome"] not in ("matched_event", "no_event", "censored",
                            "inconclusive", "not_applicable"):
        raise LedgerError("invalid_outcome")
    now = iso_time(recorded)
    verified = iso_time(p["verified_through"])
    if verified > now:
        raise LedgerError("verification_as_of_future")
    for field in ("actors_match", "action_match", "geography_match"):
        if type(p[field]) is not bool:
            raise LedgerError("invalid_matching_flag")
    if p["outcome"] == "matched_event":
        if not all(p[x] for x in ("actors_match", "action_match", "geography_match")):
            raise LedgerError("matched_event_requires_explicit_actor_action_geography_match")
        if p["event_time"] is None or iso_time(p["event_time"]) > verified:
            raise LedgerError("event_not_verified_at_adjudication")
    elif p["event_time"] is not None:
        raise LedgerError("nonmatched_outcome_has_event_time")
    if type(p["coverage_complete"]) is not bool:
        raise LedgerError("invalid_outcome_coverage_flag")
    if p["outcome"] == "no_event" and not p["coverage_complete"]:
        raise LedgerError("no_event_requires_observed_complete_risk_window")
    if p["outcome"] == "no_event" and verified < iso_time(issued["horizon_end"]):
        raise LedgerError("no_event_requires_complete_forecast_window")
    if p["revision_reason"] is not None:
        clean_string(p["revision_reason"], "revision_reason", minimum=20)


def validate_new(kind, payload, recorded, entries):
    issued = {e["payload"]["tipper_id"]: e["payload"]
              for e in entries if e["kind"] == "issued"}
    if kind == "issued":
        validate_issuance(payload, recorded)
        if payload["tipper_id"] in issued:
            raise LedgerError("tipper_id_already_issued")
    elif kind == "report":
        validate_report(payload, recorded)
        if payload["tipper_id"] not in issued:
            raise LedgerError("unknown_tipper")
    elif kind == "adjudicated":
        tipper_id = payload.get("tipper_id") if isinstance(payload, dict) else None
        if tipper_id not in issued:
            raise LedgerError("unknown_tipper")
        validate_adjudication(payload, recorded, issued[tipper_id])
        earlier = [e for e in entries if e["kind"] == "adjudicated"
                   and e["payload"]["tipper_id"] == tipper_id]
        if earlier and payload["revision_reason"] is None:
            raise LedgerError("revised_adjudication_requires_explanation")
        if not earlier and payload["revision_reason"] is not None:
            raise LedgerError("no_prior_adjudication_to_revise")
    else:
        raise LedgerError("unknown_event_kind")


def validate_log(raw):
    if len(raw) > MAX_LEDGER_BYTES:
        raise LedgerError("ledger_exceeds_size_limit")
    if raw and not raw.endswith(b"\n"):
        raise LedgerError("truncated_last_entry")
    entries = []
    head = GENESIS
    last_recorded = None
    for line in raw.splitlines():
        if len(line) > MAX_LINE_BYTES:
            raise LedgerError("oversized_ledger_entry")
        try:
            e = json.loads(line, object_pairs_hook=object_unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(LedgerError("nonfinite_json")))
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise LedgerError("invalid_ledger_json") from exc
        if (not isinstance(e, dict) or
                set(e) != {"schema", "seq", "kind", "recorded_at", "previous_hash",
                           "payload", "entry_hash"} or
                e["schema"] != SCHEMA or type(e["seq"]) is not int or
                e["seq"] != len(entries) + 1 or e["previous_hash"] != head):
            raise LedgerError("ledger_chain_structure_corrupt")
        if not isinstance(e["entry_hash"], str) or len(e["entry_hash"]) != 64:
            raise LedgerError("invalid_entry_hash")
        core = {k: v for k, v in e.items() if k != "entry_hash"}
        digest = hashlib.sha256(json_bytes(core)).hexdigest()
        if digest != e["entry_hash"]:
            raise LedgerError("ledger_hash_chain_corrupt")
        recorded = iso_time(e["recorded_at"])
        if last_recorded and recorded < last_recorded:
            raise LedgerError("recorded_time_moved_backwards")
        validate_new(e["kind"], e["payload"], e["recorded_at"], entries)
        last_recorded, head = recorded, digest
        entries.append(e)
        if len(entries) > MAX_ENTRIES:
            raise LedgerError("ledger_too_many_entries")
    return entries, head


def append(path, kind, payload, *, clock=utc_now):
    """Exclusive file lock + fsync; OS append only; no exposed backdating param."""
    if not isinstance(path, Path):
        path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_APPEND | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise LedgerError("ledger_path_not_regular")
        fcntl.flock(fd, fcntl.LOCK_EX)
        with os.fdopen(os.dup(fd), "rb") as stream:
            existing = stream.read(MAX_LEDGER_BYTES + 1)
        entries, head = validate_log(existing)
        if len(entries) >= MAX_ENTRIES:
            raise LedgerError("ledger_too_many_entries")
        recorded = clock()
        iso_time(recorded)
        if entries and iso_time(recorded) < iso_time(entries[-1]["recorded_at"]):
            raise LedgerError("local_issuer_clock_moved_backwards")
        validate_new(kind, payload, recorded, entries)
        core = {"schema": SCHEMA, "seq": len(entries) + 1,
                "kind": kind, "recorded_at": recorded,
                "previous_hash": head, "payload": payload}
        digest = hashlib.sha256(json_bytes(core)).hexdigest()
        line = json_bytes({**core, "entry_hash": digest}) + b"\n"
        if len(existing) + len(line) > MAX_LEDGER_BYTES or len(line) > MAX_LINE_BYTES:
            raise LedgerError("ledger_write_budget_exceeded")
        size_written = os.write(fd, line)
        if size_written != len(line):
            raise LedgerError("short_atomic_ledger_append")
        os.fsync(fd)
        return {"seq": core["seq"], "entry_hash": digest,
                "recorded_at": recorded, "kind": kind, "status": "appended"}
    finally:
        os.close(fd)


def read_ledger(path):
    if not path.is_file() or path.is_symlink():
        raise LedgerError("ledger_file_missing_or_symlink")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        fcntl.flock(fd, fcntl.LOCK_SH)
        with os.fdopen(os.dup(fd), "rb") as stream:
            raw = stream.read(MAX_LEDGER_BYTES + 1)
        return validate_log(raw)
    finally:
        os.close(fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("issue", "report", "adjudicate", "verify"))
    parser.add_argument("--ledger", required=True, type=Path,
                        help="Private append-only local ledger outside the Git checkout")
    parser.add_argument("--payload", type=Path, help="JSON record for issue/report/adjudicate")
    args = parser.parse_args(argv)
    try:
        checkout = Path(__file__).resolve().parents[1]
        if args.ledger.resolve().is_relative_to(checkout):
            raise LedgerError("private_ledger_must_be_outside_git_checkout")
        if args.command == "verify":
            records, head = read_ledger(args.ledger)
            print(json.dumps({"status": "verified_local_hash_chain",
                              "entries": len(records), "head_hash": head,
                              "external_timestamp_or_immutability_proven": False}))
        else:
            if args.payload is None or args.payload.resolve() == args.ledger.resolve():
                raise LedgerError("payload_missing_or_aliases_ledger")
            payload = load_json_file(args.payload)
            operation = {"issue": "issued", "report": "report",
                         "adjudicate": "adjudicated"}[args.command]
            print(json.dumps(append(args.ledger, operation, payload)))
        return 0
    except (LedgerError, OSError, TypeError, OverflowError, ValueError) as exc:
        print(json.dumps({"status": "unavailable",
                          "reason": str(exc) if isinstance(exc, LedgerError)
                          else "local_ledger_io_or_schema_failure"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
