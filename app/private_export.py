# SPDX-License-Identifier: AGPL-3.0-only
"""Private operator exports. Never log records or validation values."""

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import time
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path

import click
from jsonschema import Draft202012Validator, FormatChecker

from . import engine
from .config import ROOT
from .db import configuration_snapshot, connect, transaction
from .instrument import INSTRUMENT_VERSION, instrument_copy, make_path, validate_path

# The collection closes at an instant the operator fixes later and passes with
# --closed-at; without it nothing is closed.
PROGRAMMES = {
    "medicine": "medicine_and_surgery",
    "biotech": "biotechnology",
    "biotech_molecular": "molecular_biotechnology",
    "biotech_ai": "biotechnologies_ai_health",
    "pharmacy": "pharmacy",
    "ctf": "pharmaceutical_chemistry",
}


def programme_bucket(db, identity):
    if identity["programme"] in PROGRAMMES:
        return PROGRAMMES[identity["programme"]]
    activated = engine.amended_programmes(db).get(identity["programme"])
    if (
        identity["programme"] in engine.AMENDABLE_PROGRAMMES
        and activated is not None
        and activated <= identity["updated"]
    ):
        return engine.AMENDABLE_PROGRAMMES[identity["programme"]]["export_bucket"]
    return None


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def iso(epoch):
    # Floor rather than round: never move an event across a cutoff/closure.
    micros = int(
        (Decimal.from_float(float(epoch)) * 1_000_000).to_integral_value(rounding=ROUND_FLOOR)
    )
    seconds, fraction = divmod(micros, 1_000_000)
    return (
        datetime.fromtimestamp(seconds, UTC)
        .replace(microsecond=fraction)
        .isoformat(timespec="microseconds")
    )


def epoch(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timezone required")
    return parsed.timestamp()


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def instrument_bytes(cfg):
    # Shared with the existing instrument command; exact bytes, not a second digest convention.
    return json_bytes(
        {
            "instrument_version": INSTRUMENT_VERSION,
            "pipeline_version": cfg["PIPELINE_VERSION"],
            "wording": {lang: instrument_copy(lang) for lang in ("it", "en")},
            "example_paths": {label: make_path(label) for label in engine.LABELS},
            "validation_source": "app/instrument.py",
            "presentation_source": "app/presentation.py",
        }
    )


def readonly(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


def metadata(db):
    return dict(db.execute("SELECT key,value FROM metadata"))


def validate(value, schema):
    spec = json.loads((ROOT / "docs/export" / (schema + ".schema.json")).read_text())
    if next(Draft202012Validator(spec, format_checker=FormatChecker()).iter_errors(value), None):
        # jsonschema's default error includes the offending private record.
        raise ValueError("Private export schema validation failed")


@contextmanager
def private_directory(output):
    """Publish a complete new bundle; never replace an earlier snapshot/export."""
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("Output must be a new directory")
    output.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".private-export-", dir=output.parent))
    try:
        yield staging
        # Refuse even an empty existing destination (including a concurrent export).
        if output.exists() or output.is_symlink():
            raise ValueError("Output already exists")
        staging.rename(output)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def private_write(path, data):
    with path.open("xb") as stream:
        os.chmod(path, 0o600)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def year_bucket(value):
    if value is None or not value.strip():
        return None
    numbers = re.findall(r"[+-]?\d+", value)
    return str(int(numbers[0])) if len(numbers) == 1 and 1 <= int(numbers[0]) <= 6 else "other"


def eligibility(db, sid, cutoff):
    identity = db.execute(
        "SELECT programme,year,eligibility_declared,needs_review,updated FROM identities "
        "WHERE session_id=? AND preview=0",
        (sid,),
    ).fetchone()
    pending = {"eligible": None, "confirmed_at": None, "basis": "pending"}
    if identity is None:
        return pending, None
    decision = db.execute(
        "SELECT action,created FROM audit WHERE session_id=? AND preview=0 "
        "AND action IN ('eligibility-approve','eligibility-reject') "
        "AND created<=? ORDER BY created DESC,id DESC LIMIT 1",
        (sid, cutoff),
    ).fetchone()
    if decision:
        return {
            "eligible": decision["action"] == "eligibility-approve",
            "confirmed_at": iso(decision["created"]),
            "basis": "operator_review",
        }, identity
    # An amended programme counts only for declarations made after its activation.
    activated = engine.amended_programmes(db).get(identity["programme"])
    if identity["programme"] not in engine.AMENDABLE_PROGRAMMES:
        activated = None
    if (
        identity["eligibility_declared"] == 1
        and (
            identity["programme"] in PROGRAMMES
            or (activated is not None and activated <= identity["updated"])
        )
        and identity["needs_review"] == 0
        and identity["updated"] <= cutoff
    ):
        return {
            "eligible": True,
            "confirmed_at": iso(identity["updated"]),
            "basis": "adult_unipi_approved_programme",
        }, identity
    return pending, identity


def answer_rows(db, cutoff):
    # Same slot selection as engine.votes/export-answers, limited to the cutoff
    # BEFORE selecting the earliest accepted answer in each slot.
    counted = set()
    for item in db.execute("SELECT id FROM items"):
        slots = set()
        for row in db.execute(
            """SELECT a.id,a.slot FROM answers a JOIN sessions s ON s.id=a.session_id
            LEFT JOIN identities i ON i.session_id=s.id
            WHERE a.item_id=? AND a.kind='real' AND a.paid=1 AND s.excluded=0
            AND COALESCE(i.needs_review,0)=0 AND a.preview=0 AND a.submitted<=?
            ORDER BY a.submitted,a.id""",
            (item[0], cutoff),
        ):
            if row["slot"] not in slots:
                counted.add(row["id"])
                slots.add(row["slot"])
    rows = []
    for row in db.execute(
        """SELECT a.*,s.excluded,s.quality_failed,t.created AS assigned
        FROM answers a JOIN sessions s ON s.id=a.session_id
        JOIN assignments t ON t.id=a.assignment_id
        WHERE a.kind='real' AND a.preview=0 AND a.submitted<=? ORDER BY a.id""",
        (cutoff,),
    ):
        data = {
            "item_id": row["item_id"],
            "read_id": row["assignment_id"],
            **{
                k: row[k]
                for k in (
                    "instrument_version",
                    "pipeline_version",
                    "relevance",
                    "other_detail",
                    "binary_inconsistent",
                    "package_sha256",
                    "config_sha256",
                )
            },
            "path": json.loads(row["path"]),
            "field_problems": json.loads(row["field_problems"]),
            "session_pseudonym": row["session_id"],
            "label": row["label"],
            "factor": row["factor"],
            "rationale": row["rationale"],
            "time_on_item_seconds": row["seconds"],
            "submitted_at_utc": iso(row["submitted"]),
            "assigned_at_utc": iso(row["assigned"]),
            **{k: row[k] for k in ("paid", "replacement", "surplus", "excluded", "quality_failed")},
            "counted": int(row["id"] in counted),
            "preview": row["preview"],
        }
        validate(data, "student_answer_row")
        derived = validate_path(data["path"], data["rationale"])
        if any(data[key] != value for key, value in derived.items()):
            raise ValueError("Stored answer derivation differs from instrument")
        if data["paid"] == data["surplus"] or (
            data["counted"] and (not data["paid"] or data["surplus"] or data["excluded"])
        ):
            raise ValueError("Incoherent answer flags")
        rows.append(data)
    return rows


# Participant corrections after submission. The answers row is
# never modified: a correction is an audit row whose reason is this JSON record, and
# the export publishes it next to the answers, never in their place.
CORRECTION_TYPE = "participant_correction_after_submission"
CORRECTION_KEYS = {
    "type",
    "answer_id",
    "item_id",
    "answers_row_modified",
    "source",
    "disclosure",
    "recorded_by",
    "changes",
    "derived_old",
    "derived_new",
    "derived_with",
    "corrected_path",
}
DERIVED = ("label", "factor", "binary_inconsistent")


def derived_summary(value):
    return {
        "label": value["label"],
        "factor": value["factor"],
        "binary_inconsistent": bool(value["binary_inconsistent"]),
    }


def path_changes(old, new):
    """Changed answers at question level: q1.<side>.<check>, q2.<check>, other keys."""
    changes = {}
    for side in ("a", "b"):
        before = (old.get("q1") or {}).get(side) or {}
        after = (new.get("q1") or {}).get(side) or {}
        for field in sorted(set(before) | set(after)):
            if before.get(field) != after.get(field):
                changes[f"q1.{side}.{field}"] = {"old": before.get(field), "new": after.get(field)}
    before, after = old.get("q2") or {}, new.get("q2") or {}
    for field in sorted(set(before) | set(after)):
        if before.get(field) != after.get(field):
            changes[f"q2.{field}"] = {"old": before.get(field), "new": after.get(field)}
    for key in sorted((set(old) | set(new)) - {"q1", "q2"}):
        if old.get(key) != new.get(key):
            changes[key] = {"old": old.get(key), "new": new.get(key)}
    return changes


def correction_record(audit):
    record = json.loads(audit["reason"])
    # A later entry in a chain may omit the disclosure; it inherits the previous one.
    required = CORRECTION_KEYS - (
        {"disclosure"} if isinstance(record, dict) and record.get("supersedes_audit_id") else set()
    )
    if (
        not isinstance(record, dict)
        or not required <= record.keys()
        or record["type"] != CORRECTION_TYPE
        or record["answers_row_modified"] is not False
        or not isinstance(record["answer_id"], int)
        or not isinstance(record["corrected_path"], dict)
        or not isinstance(record.get("supersedes_audit_id"), (int, type(None)))
        or isinstance(record.get("supersedes_audit_id"), bool)
        # Optional: the full note in force after this entry (absent: the note is unchanged).
        or not isinstance(record.get("corrected_rationale", ""), str)
    ):
        raise ValueError("Malformed participant correction")
    derived_summary(record["derived_old"])
    derived_summary(record["derived_new"])
    return record


# Self-service corrections on the site: the same record as the
# operator command, built by write_correction, with these fixed provenance fields.
SELF_SERVICE_SOURCE = "self-service correction on the site"
SELF_SERVICE_RECORDED_BY = "participant"


def self_service_disclosure(cfg):
    """What the participant had in front of them on the site's correction page."""
    return (
        "Site correction page: the pair and questions with the instrument wording in force "
        f"(instrument export sha256 {sha256(instrument_bytes(cfg))}), pre-filled with the "
        "latest answer, under the notice that the original answer stays recorded and pay "
        "does not change"
    )


def correction_chain(db, answer):
    """Recorded corrections of one answer, oldest first, as (audit row, record) pairs."""
    chain = []
    for audit in db.execute(
        "SELECT id,reason,created FROM audit WHERE action='participant-correction' "
        "AND session_id=? ORDER BY created,id",
        (answer["session_id"],),
    ):
        record = json.loads(audit["reason"])
        if record.get("answer_id") == answer["id"]:
            chain.append((audit, record))
    return chain


def answer_in_force(db, answer):
    """The latest version of an answer: its last correction, else the submitted answer."""
    chain = correction_chain(db, answer)
    rationale = answer["rationale"]
    for _, record in chain:
        rationale = record.get("corrected_rationale", rationale)
    if not chain:
        return {
            "path": json.loads(answer["path"]),
            "rationale": rationale,
            "derived": derived_summary(answer),
            "audit_id": None,
            "corrected_at": None,
        }
    audit, last = chain[-1]
    return {
        "path": last["corrected_path"],
        "rationale": rationale,
        "derived": derived_summary(last["derived_new"]),
        "audit_id": audit["id"],
        "corrected_at": audit["created"],
    }


def write_correction(
    db, cfg, answer, corrected_path, *, source, disclosure, recorded_by, rationale=None, now=None
):
    """Append one correction to an answer's chain, inside the caller's transaction.

    Shared by `flask record-correction` and the site. The answers row is never modified.
    The new entry supersedes the latest one and carries the full cumulative path and note;
    `rationale=None` keeps the note in force. Returns None, writing nothing, when the
    corrected answer equals the latest version.
    """
    current = answer_in_force(db, answer)
    derived = validate_path(
        corrected_path, current["rationale"] if rationale is None else rationale
    )
    changes = path_changes(current["path"], derived["path"])
    if derived["rationale"] != current["rationale"]:
        changes["rationale"] = {"old": current["rationale"], "new": derived["rationale"]}
    if not changes:
        return None
    last_id = current["audit_id"]
    reason = {
        "type": CORRECTION_TYPE,
        "answer_id": answer["id"],
        "item_id": answer["item_id"],
        "answers_row_modified": False,
        "source": source,
        "disclosure": disclosure,
        "recorded_by": recorded_by,
        "changes": changes,
        "changes_relative_to": "original answer"
        if last_id is None
        else f"corrected_path of audit {last_id}",
        "supersedes_audit_id": last_id,
        "derived_old": current["derived"],
        "derived_new": derived_summary(derived),
        "derived_with": {
            "instrument_version": INSTRUMENT_VERSION,
            "instrument_export_sha256": sha256(instrument_bytes(cfg)),
        },
        "corrected_path": derived["path"],
        "corrected_rationale": derived["rationale"],
    }
    now = time.time() if now is None else now
    # The export orders a chain by time: never date an entry before the one it replaces.
    created = max(now, current["corrected_at"] or now)
    cur = db.execute(
        "INSERT INTO audit(session_id,action,reason,created) VALUES(?,?,?,?)",
        (
            answer["session_id"],
            "participant-correction",
            json.dumps(reason, ensure_ascii=False, sort_keys=True),
            created,
        ),
    )
    return {"audit_id": cur.lastrowid, "changes": changes, "supersedes_audit_id": last_id}


def correction_rows(db, cutoff, rows):
    """Correction chains per answer, up to the cutoff; the last entry is the one applied.

    Each later entry names the entry it replaces (supersedes_audit_id) and carries the
    full cumulative corrected path. A chain must be linear, within one answer and one
    session; the applied entry is revalidated with the instrument.
    """
    exported = {(row["session_pseudonym"], row["read_id"]) for row in rows}
    chains = {}
    for audit in db.execute(
        "SELECT id,session_id,reason,created FROM audit WHERE action='participant-correction' "
        "AND preview=0 AND created<=? ORDER BY created,id",
        (cutoff,),
    ):
        record = correction_record(audit)
        chains.setdefault(record["answer_id"], []).append((audit, record))
    out = []
    for answer_id, chain in sorted(chains.items()):
        answer = db.execute(
            "SELECT id,session_id,item_id,assignment_id,label,factor,binary_inconsistent,"
            "rationale FROM answers WHERE id=?",
            (answer_id,),
        ).fetchone()
        if answer is None:
            raise ValueError("Participant correction for a missing answer")
        previous, disclosure, rationale = None, None, answer["rationale"]
        for audit, record in chain:
            disclosure = record.setdefault("disclosure", disclosure)
            # The note in force: an entry without corrected_rationale keeps the previous one.
            rationale = record.setdefault("corrected_rationale", rationale)
            if (
                audit["session_id"] != answer["session_id"]
                or record["item_id"] != answer["item_id"]
                or record.get("supersedes_audit_id") != previous
            ):
                raise ValueError("Participant correction chain is not linear for its answer")
            previous = audit["id"]
        if derived_summary(chain[0][1]["derived_old"]) != derived_summary(answer):
            raise ValueError("Participant correction does not start from the stored answer")
        last_audit, last = chain[-1]
        derived = validate_path(last["corrected_path"], last["corrected_rationale"])
        if derived_summary(derived) != derived_summary(last["derived_new"]):
            raise ValueError("Participant correction derivation mismatch")
        # Corrections of reads outside this export (practice, retired pairs) stay in the
        # database; they cannot change any exported row.
        if (answer["session_id"], answer["assignment_id"]) not in exported:
            continue
        for audit, record in chain:
            applied = audit["id"] == last_audit["id"]
            row = {
                "audit_id": audit["id"],
                "recorded_at_utc": iso(audit["created"]),
                "session_pseudonym": answer["session_id"],
                "read_id": answer["assignment_id"],
                "item_id": answer["item_id"],
                "applied": applied,
                "supersedes_audit_id": record.get("supersedes_audit_id"),
                "changes_relative_to": record.get("changes_relative_to", "original answer"),
                "corrected_path": derived["path"] if applied else record["corrected_path"],
                "corrected_rationale": derived["rationale"]
                if applied
                else record["corrected_rationale"],
                "derived_old": derived_summary(record["derived_old"]),
                "derived_new": derived_summary(derived if applied else record["derived_new"]),
                "changes": record["changes"],
                "source": record["source"],
                "disclosure": record["disclosure"],
                "recorded_by": record["recorded_by"],
                "derived_with": record["derived_with"],
            }
            validate(row, "participant_correction")
            out.append(row)
    return out


def check_lock(lock, frozen, reference):
    validate(lock, "human_collection_lock")

    def safe(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if any(word in key.lower() for word in ("secret", "password", "token", "api_key")):
                    raise ValueError("Secret key in configuration lock")
                safe(item)
        elif isinstance(value, list):
            for item in value:
                safe(item)

    safe(lock["configuration_snapshot"])
    if (
        sha256(canonical_bytes(lock["configuration_snapshot"])) != frozen["config_sha256"]
        or lock["site_configuration_sha256"] != frozen["config_sha256"]
        or lock["reference_revision_sha256"] != reference
    ):
        raise ValueError("Collection lock hash mismatch")
    return epoch(lock["locked_at"])


def build_export(db, cfg, cutoff, human_hash, reference_hash, lock_bytes, closed_at=None):
    frozen = metadata(db)
    locked = check_lock(json.loads(lock_bytes), frozen, reference_hash)
    # Reads of pairs retired by a package rebase carry the previous package hash; they
    # are pilot data and stay in the database and its snapshots, not in this export.
    live = {r[0] for r in db.execute("SELECT id FROM items WHERE retired=0")}
    rows = [row for row in answer_rows(db, cutoff) if row["item_id"] in live]
    states, identities = {}, {}
    for sid in sorted({row["session_pseudonym"] for row in rows}):
        states[sid], identities[sid] = eligibility(db, sid, cutoff)
    accepted = {
        row["session_pseudonym"]
        for row in rows
        if row["paid"]
        and not row["surplus"]
        and states[row["session_pseudonym"]]["eligible"] is True
    }
    demographics = {
        "population": "unique_sessions_with_accepted_eligible_real_read",
        "sessions": len(accepted),
        "programme": {},
        "year": {},
        "programme_missing": 0,
        "year_missing": 0,
    }
    for sid in sorted(accepted):
        identity = identities[sid]
        for key, bucket in (
            ("programme", programme_bucket(db, identity)),
            ("year", year_bucket(identity["year"])),
        ):
            if bucket is None:
                demographics[key + "_missing"] += 1
            else:
                demographics[key][bucket] = demographics[key].get(bucket, 0) + 1
    formatted_cutoff = epoch(iso(cutoff))
    for row in rows:
        if (
            not locked
            <= epoch(row["assigned_at_utc"])
            <= epoch(row["submitted_at_utc"])
            <= formatted_cutoff
        ):
            raise ValueError("Answer timestamps do not match collection lock and cutoff")
        if (
            row["package_sha256"] != frozen["pair_sha256"]
            or row["config_sha256"] != frozen["config_sha256"]
        ):
            raise ValueError("Answer provenance mismatch")
    answers = b"".join(
        (json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n").encode() for row in rows
    )
    corrections = b"".join(
        (json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n").encode()
        for row in correction_rows(db, cutoff, rows)
    )
    exported = time.time()
    companion = {
        "schema_version": 2,
        "pipeline_version": "2.0",
        "instrument_version": "2.0",
        "human_package_sha256": human_hash,
        "site_pair_package_sha256": frozen["pair_sha256"],
        "site_configuration_sha256": frozen["config_sha256"],
        "site_instrument_sha256": sha256(instrument_bytes(cfg)),
        "answers_sha256": sha256(answers),
        "participant_corrections": corrections.count(b"\n"),
        "participant_corrections_sha256": sha256(corrections),
        "human_collection_lock_sha256": sha256(lock_bytes),
        "reference_revision_sha256": reference_hash,
        "snapshot_at": iso(cutoff),
        "exported_at": iso(exported),
        "collection_closed": closed_at is not None and cutoff >= closed_at,
        "eligibility": states,
        "demographics": demographics,
    }
    if cutoff > exported or locked > cutoff:
        raise ValueError("Snapshot or lock is in the future")
    # Automatic/manual exclusions share an audit action; their history cannot be
    # separated exactly. Omit flag_history rather than inventing aggregate zeros.
    validate(companion, "student_export_metadata")
    return answers, json_bytes(companion), companion, len(rows), corrections


def register(app):
    def guarded(function):
        from functools import wraps

        @wraps(function)
        def run(*args, **kwargs):
            try:
                return function(*args, **kwargs)
            except (ValueError, KeyError, TypeError, OSError, sqlite3.Error, OverflowError):
                raise click.ClickException(
                    "Private operation refused: check inputs, provenance, timestamps, schemas and output destination. No private records were logged."
                ) from None

        return run

    @app.cli.command("config-snapshot")
    @click.option("--output", required=True, type=click.Path(path_type=Path))
    @guarded
    def config_snapshot(output):
        data = canonical_bytes(configuration_snapshot(app.config))
        with closing(readonly(app.config["DATABASE_PATH"])) as db:
            if sha256(data) != metadata(db)["config_sha256"]:
                raise ValueError("Configuration hash mismatch")
        output.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        # One file, atomic publication, never overwrite an existing lock input.
        with tempfile.TemporaryDirectory(prefix=".private-config-", dir=output.parent) as tmp:
            staged = Path(tmp) / "configuration.json"
            private_write(staged, data)
            os.link(staged, output)
        click.echo(sha256(data))

    @app.cli.command("record-correction")
    @click.option("--answer-id", type=int, required=True)
    @click.option(
        "--corrected-path",
        "corrected_file",
        required=True,
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        help="JSON file with the full corrected answer path",
    )
    @click.option("--source", required=True, help="Where the participant asked for it")
    @click.option("--disclosure", required=True, help="What the participant was told")
    @click.option("--recorded-by", required=True)
    @guarded
    def record_correction(answer_id, corrected_file, source, disclosure, recorded_by):
        """Record a participant's correction after submission; the answer row is never modified."""
        corrected = json.loads(corrected_file.read_text())
        with closing(connect(app.config)) as db, transaction(db):
            answer = db.execute("SELECT * FROM answers WHERE id=?", (answer_id,)).fetchone()
            if answer is None:
                raise ValueError("Unknown answer")
            # The note in force is kept; only the participant can change it, on the site.
            written = write_correction(
                db,
                app.config,
                answer,
                corrected,
                source=source,
                disclosure=disclosure,
                recorded_by=recorded_by,
            )
            if written is None:
                raise ValueError("The corrected path changes nothing")
        click.echo(
            json.dumps(
                {
                    "audit_id": written["audit_id"],
                    "answer_id": answer_id,
                    "changed": sorted(written["changes"]),
                    "supersedes_audit_id": written["supersedes_audit_id"],
                }
            )
        )

    @app.cli.command("export")
    @click.option("--output", required=True, type=click.Path(path_type=Path))
    @click.option("--database", type=click.Path(path_type=Path))
    @click.option("--human-package-sha256", required=True)
    @click.option("--reference-revision-sha256", required=True)
    @click.option("--lock-file", required=True, type=click.Path(path_type=Path))
    @click.option(
        "--closed-at",
        help="Signed collection closure instant, timezone-aware ISO 8601; omit while open",
    )
    @guarded
    def export_bundle(
        output, database, human_package_sha256, reference_revision_sha256, lock_file, closed_at
    ):
        """Write the private analysis export: answer rows, metadata and corrections."""
        closed_at = epoch(closed_at) if closed_at else None
        lock_bytes = lock_file.read_bytes()
        cutoff = None
        if database is not None:
            sidecar = json.loads(database.with_name("snapshot.json").read_bytes())
            cutoff = epoch(sidecar["snapshot_at"])
            taken = epoch(sidecar["taken_at"])
            if sidecar["source"] != "sqlite-backup" or not cutoff <= taken <= time.time():
                raise ValueError("Invalid snapshot sidecar")
        with closing(readonly(database or app.config["DATABASE_PATH"])) as db:
            db.execute("BEGIN")
            metadata(db)  # Pin the SQLite read snapshot before choosing the live cutoff.
            if cutoff is None:
                cutoff = time.time()
            answers, meta_bytes, companion, count, corrections = build_export(
                db,
                app.config,
                cutoff,
                human_package_sha256,
                reference_revision_sha256,
                lock_bytes,
                closed_at,
            )
            db.commit()
        with private_directory(output) as staging:
            private_write(staging / "answers.jsonl", answers)
            private_write(staging / "metadata.json", meta_bytes)
            private_write(staging / "corrections.jsonl", corrections)
        if companion["collection_closed"]:
            # The immutable snapshot remains read-only. Guard the configured live DB.
            with (
                closing(
                    sqlite3.connect(
                        Path(app.config["DATABASE_PATH"]).resolve().as_uri() + "?mode=rw",
                        uri=True,
                        isolation_level=None,
                    )
                ) as db,
                transaction(db),
            ):
                frozen = metadata(db)
                if (
                    frozen["pair_sha256"] != companion["site_pair_package_sha256"]
                    or frozen["config_sha256"] != companion["site_configuration_sha256"]
                ):
                    raise ValueError("Final export is for a different live collection")
                for key, value in (
                    ("final_export_answers_sha256", sha256(answers)),
                    ("final_export_metadata_sha256", sha256(meta_bytes)),
                    ("final_export_corrections_sha256", sha256(corrections)),
                ):
                    db.execute(
                        "INSERT OR REPLACE INTO metadata(key,value) VALUES(?,?)", (key, value)
                    )
        click.echo(
            json.dumps(
                {
                    "answers": count,
                    "sessions": len(companion["eligibility"]),
                    "answers_sha256": sha256(answers),
                    "metadata_sha256": sha256(meta_bytes),
                    "participant_corrections": companion["participant_corrections"],
                }
            )
        )

    @app.cli.command("snapshot-db")
    @click.option("--at", required=True, help="Earliest capture time, timezone-aware ISO 8601")
    @click.option("--output", required=True, type=click.Path(path_type=Path))
    @guarded
    def snapshot_db(at, output):
        requested = epoch(at)
        if time.time() < requested:
            raise ValueError("Capture time has not arrived")
        with private_directory(output) as staging:
            path = staging / "app.sqlite3"
            private_write(path, b"")
            with closing(readonly(app.config["DATABASE_PATH"])) as source:
                source.execute("BEGIN")
                metadata(source)  # Establish one WAL read view; writers remain free.
                captured = time.time()
                exact = 0 <= captured - requested <= EXACT_INSTANT_SECONDS and unchanged_since(
                    source, requested
                )
                with closing(sqlite3.connect(path)) as target:
                    source.backup(target, pages=256)
                source.commit()
            taken = time.time()
            sidecar = {
                # The registered cutoff itself when nothing the export reads changed
                # between it and the read view; otherwise the true capture time.
                "snapshot_at": iso(requested if exact else captured),
                "captured_at": iso(captured),
                "taken_at": iso(taken),
                "source": "sqlite-backup",
                "exact_instant": exact,
            }
            private_write(staging / "snapshot.json", json_bytes(sidecar))
            digest = sha256(path.read_bytes())
        click.echo(
            json.dumps(
                {
                    "snapshot_at": sidecar["snapshot_at"],
                    "taken_at": sidecar["taken_at"],
                    "sha256": digest,
                }
            )
        )


EXACT_INSTANT_SECONDS = 300


def unchanged_since(db, cutoff):
    """True when the exported state at the read view equals the state at cutoff.

    Answer rows are immutable and are filtered by the cutoff, and a later answer
    cannot displace an earlier counted slot. Session flags change only with an
    audit row (engine.exclude), and eligibility only with an identity update or
    an audit row. So no audit row and no identity update after the cutoff means
    every exported value is the one that held at the cutoff.
    """
    return not (
        db.execute("SELECT 1 FROM audit WHERE created>? LIMIT 1", (cutoff,)).fetchone()
        or db.execute("SELECT 1 FROM identities WHERE updated>? LIMIT 1", (cutoff,)).fetchone()
    )


def create_operator_app(overrides=None):
    """CLI-only factory: never initialize or migrate the configured live database.

    In particular, exporting a backup must work without opening the live DB.
    A final export explicitly opens it only to record the required purge receipt.
    """
    from flask import Flask

    from .cli import register as register_commands
    from .config import settings

    app = Flask(__name__)
    app.config.update(settings(overrides))
    register_commands(app)
    return app
