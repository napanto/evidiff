# SPDX-License-Identifier: AGPL-3.0-only
"""Only temporary synthetic databases; never use the operator's database."""

import json
import sqlite3
from datetime import datetime

import pytest
from conftest import session

from app import private_export as export
from app.db import configuration_snapshot, connect
from app.instrument import make_path, validate_path

NOON = export.epoch("2026-11-15T12:00:00+01:00")


@pytest.fixture
def data(app, tmp_path, monkeypatch):
    monkeypatch.setattr(export.time, "time", lambda: NOON)
    db = connect(app.config)
    lock = {
        "schema_version": 1,
        "status": "locked",
        "evaluation_config_sha256": "e" * 64,
        "configuration_snapshot": configuration_snapshot(app.config),
        "site_configuration_sha256": export.metadata(db)["config_sha256"],
        "locked_at": export.iso(NOON - 1000),
        "frozen_before_first_real_student_read": True,
        "deployment_confirmed_by": "Synthetic operator",
        "scientific_rules_match_registered_protocol": True,
        "reference_revision_sha256": "r" * 64,
    }
    # SHA256 codes use hexadecimal only.
    lock["reference_revision_sha256"] = "a" * 64
    lock_file = tmp_path / "lock.json"
    lock_file.write_bytes(export.json_bytes(lock))
    yield app.test_cli_runner(), db, lock_file
    db.close()


def add_answer(db, *, sid=None, submitted=NOON, preview=0, paid=1, surplus=0, slot=1):
    sid = sid or session(db, NOON - 200)
    index = db.execute("SELECT COUNT(*) FROM answers").fetchone()[0]
    item = db.execute(
        "SELECT id FROM items ORDER BY id LIMIT 1 OFFSET ?", (index % 24,)
    ).fetchone()[0]
    aid = f"synthetic-read-{index}"
    db.execute(
        "INSERT INTO assignments(id,session_id,item_id,kind,slot,position,state,created) "
        "VALUES(?,?,?,'real',?,?,'answered',?)",
        (aid, sid, item, slot, index, NOON - 50.123456),
    )
    path = validate_path(make_path("concordant"), "Synthetic annotation rationale")
    frozen = export.metadata(db)
    row = {
        "assignment_id": aid,
        "session_id": sid,
        "item_id": item,
        "kind": "real",
        "slot": slot,
        **path,
        "path": json.dumps(path["path"]),
        "field_problems": json.dumps(path["field_problems"]),
        "seconds": 50,
        "submitted": submitted,
        "paid": paid,
        "surplus": surplus,
        "preview": preview,
        "pipeline_version": "2.0",
        "package_sha256": frozen["pair_sha256"],
        "config_sha256": frozen["config_sha256"],
    }
    db.execute(
        f"INSERT INTO answers({','.join(row)}) VALUES({','.join('?' for _ in row)})",
        list(row.values()),
    )
    return sid


def identify(db, sid, programme="medicine", year="3", declared=1, review=0, updated=NOON - 10):
    db.execute(
        "INSERT INTO identities(session_id,first_name,last_name,programme,year,needs_review,"
        "eligibility_declared,other_programme,updated) VALUES(?,?,?,?,?,?,?,?,?)",
        (
            sid,
            "SECRET_SYNTHETIC_NAME",
            "SECRET_SYNTHETIC_SURNAME",
            programme,
            year,
            review,
            declared,
            "SECRET_SYNTHETIC_OTHER",
            updated,
        ),
    )


def audit(db, sid, decision, when):
    db.execute(
        "INSERT INTO audit(session_id,action,reason,created) VALUES(?,?,?,?)",
        (sid, "eligibility-" + decision, "SECRET_SYNTHETIC_REVIEW", when),
    )


# Test closure instant; production passes the signed one with --closed-at.
CLOSURE = datetime.fromisoformat("2026-11-15T18:30:00+01:00").timestamp()


def run_export(data, output, database=None, closed_at=CLOSURE):
    runner, _, lock = data
    args = [
        "export",
        "--output",
        str(output),
        "--human-package-sha256",
        "b" * 64,
        "--reference-revision-sha256",
        "a" * 64,
        "--lock-file",
        str(lock),
    ]
    if database:
        args += ["--database", str(database)]
    if closed_at is not None:
        args += ["--closed-at", export.iso(closed_at)]
    return runner.invoke(args=args)


def test_late_payment_never_changes_either_export(data, tmp_path):
    runner, db, _ = data
    add_answer(db, paid=0, surplus=1)
    before = tmp_path / "before-late"
    assert run_export(data, before).exit_code == 0
    legacy_before = tmp_path / "legacy-before-late"
    assert runner.invoke(args=["export-answers", "--output", str(legacy_before)]).exit_code == 0
    db.execute("UPDATE answers SET late_paid=1")
    after = tmp_path / "after-late"
    result = run_export(data, after)
    assert result.exit_code == 0, result.output
    legacy_after = tmp_path / "legacy-after-late"
    assert runner.invoke(args=["export-answers", "--output", str(legacy_after)]).exit_code == 0
    for first, second in ((before, after), (legacy_before, legacy_after)):
        assert (first / "answers.jsonl").read_bytes() == (second / "answers.jsonl").read_bytes()
        row = json.loads((second / "answers.jsonl").read_text())
        assert len(row) == 25 and "late_paid" not in row
        assert (row["paid"], row["surplus"], row["counted"]) == (0, 1, 0)
    assert (legacy_before / "answers.csv").read_bytes() == (
        legacy_after / "answers.csv"
    ).read_bytes()


def read_bundle(path):
    return (
        [json.loads(line) for line in (path / "answers.jsonl").read_text().splitlines()],
        json.loads((path / "metadata.json").read_text()),
    )


def test_rows_cutoff_hashes_schemas_and_private_modes(data, app, tmp_path):
    runner, db, lock = data
    sid = add_answer(db, submitted=NOON - 0.000001)
    identify(db, sid)
    add_answer(db, submitted=NOON + 0.000001)
    add_answer(db, preview=1)
    output = tmp_path / "bundle"
    result = run_export(data, output)
    assert result.exit_code == 0, result.output
    rows, meta = read_bundle(output)
    assert len(rows) == 1 and len(rows[0]) == 25
    export.validate(rows[0], "student_answer_row")
    export.validate(meta, "student_export_metadata")
    assert rows[0]["submitted_at_utc"].endswith("59.999999+00:00")
    assert rows[0]["assigned_at_utc"].endswith("09.876543+00:00")
    assert meta["snapshot_at"] == export.iso(NOON) and not meta["collection_closed"]
    assert meta["answers_sha256"] == export.sha256((output / "answers.jsonl").read_bytes())
    assert meta["human_collection_lock_sha256"] == export.sha256(lock.read_bytes())
    instrument = tmp_path / "instrument.json"
    assert runner.invoke(args=["instrument", "--output", str(instrument)]).exit_code == 0
    assert meta["site_instrument_sha256"] == export.sha256(instrument.read_bytes())
    assert meta["site_pair_package_sha256"] == export.metadata(db)["pair_sha256"]
    assert meta["site_configuration_sha256"] == export.metadata(db)["config_sha256"]
    assert set(meta["eligibility"]) == {sid}
    assert "flag_history" not in meta
    assert output.stat().st_mode & 0o777 == 0o700
    for file in output.iterdir():
        assert file.stat().st_mode & 0o777 == 0o600
        assert "SECRET_SYNTHETIC" not in file.read_text()
    assert sid not in result.output and "Synthetic annotation" not in result.output
    assert "SECRET_SYNTHETIC" not in result.output
    assert run_export(data, output).exit_code != 0


@pytest.mark.parametrize(
    "programme,declared,review,decisions,expected,basis",
    [
        (None, 0, 0, [], None, "pending"),
        ("medicine", 1, 0, [], True, "adult_unipi_approved_programme"),
        ("medicine", 0, 0, [], None, "pending"),
        ("other", 1, 0, [], None, "pending"),
        ("medicine", 1, 1, [], None, "pending"),
        ("other", 1, 1, [("approve", -5)], True, "operator_review"),
        ("medicine", 1, 0, [("reject", -5)], False, "operator_review"),
        ("medicine", 1, 1, [("reject", -4), ("approve", -5)], False, "operator_review"),
        ("medicine", 1, 1, [("reject", -5), ("approve", -4)], True, "operator_review"),
        ("medicine", 1, 1, [("reject", -5), ("approve", -5)], True, "operator_review"),
        (None, 0, 0, [("approve", -5)], None, "pending"),
        ("medicine", 1, 1, [("approve", 1)], None, "pending"),
    ],
)
def test_eligibility_branches(
    data, tmp_path, programme, declared, review, decisions, expected, basis
):
    _, db, _ = data
    sid = add_answer(db)
    if programme is not None:
        identify(db, sid, programme=programme, declared=declared, review=review)
    for decision, offset in decisions:
        audit(db, sid, decision, NOON + offset)
    output = tmp_path / "bundle"
    assert run_export(data, output).exit_code == 0
    state = read_bundle(output)[1]["eligibility"][sid]
    assert state["eligible"] is expected and state["basis"] == basis
    assert (state["confirmed_at"] is None) == (expected is None)
    if basis == "operator_review":
        assert state["confirmed_at"] == export.iso(NOON + max(offset for _, offset in decisions))


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1", "1"),
        ("secondo anno 2", "2"),
        ("anno 3", "3"),
        ("4°", "4"),
        ("5 fuori corso", "5"),
        ("6", "6"),
        ("", None),
        ("  ", None),
        (None, None),
        ("2026", "other"),
        ("1 o 2", "other"),
        ("3 di 2026", "other"),
        ("primo", "other"),
        ("7", "other"),
        ("0", "other"),
        ("11", "other"),
        ("3 e 3", "other"),
    ],
)
def test_year_mapping(value, expected):
    assert export.year_bucket(value) == expected


def test_demographics_unique_accepted_eligible_with_excluded_and_missing(data, tmp_path):
    _, db, _ = data
    for index, programme in enumerate(export.PROGRAMMES):
        sid = add_answer(db)
        identify(db, sid, programme, str(index + 1))
        if index == 0:
            add_answer(db, sid=sid)  # Count session once.
            db.execute("UPDATE sessions SET excluded=1,quality_failed=1 WHERE id=?", (sid,))
    other = add_answer(db)
    identify(db, other, "other", "")
    audit(db, other, "approve", NOON - 1)
    odd = add_answer(db)
    identify(db, odd, "pharmacy", "third year")
    for paid, surplus, eligible in [(0, 1, True), (1, 0, False)]:
        sid = add_answer(db, paid=paid, surplus=surplus)
        if eligible:
            identify(db, sid)
    output = tmp_path / "bundle"
    assert run_export(data, output).exit_code == 0
    rows, meta = read_bundle(output)
    demo = meta["demographics"]
    assert demo["sessions"] == 8
    assert demo["programme"] == {**dict.fromkeys(export.PROGRAMMES.values(), 1), "pharmacy": 2}
    assert demo["year"] == {**dict.fromkeys("123456", 1), "other": 1}
    assert demo["programme_missing"] == demo["year_missing"] == 1
    for key in ("programme", "year"):
        assert sum(demo[key].values()) + demo[key + "_missing"] == demo["sessions"]
    assert any(row["excluded"] and row["quality_failed"] for row in rows)
    assert any(row["surplus"] for row in rows)


def backup(db, path, cutoff=NOON):
    path.parent.mkdir()
    with sqlite3.connect(path) as target:
        db.backup(target)
    path.with_name("snapshot.json").write_bytes(
        export.json_bytes(
            {
                "snapshot_at": export.iso(cutoff),
                "taken_at": export.iso(cutoff),
                "source": "sqlite-backup",
            }
        )
    )


def test_snapshot_readonly_and_missing_sidecar(data, app, tmp_path):
    _, db, _ = data
    sid = add_answer(db)
    identify(db, sid)
    saved = tmp_path / "saved" / "app.sqlite3"
    backup(db, saved)
    original = saved.read_bytes()
    saved.chmod(0o400)
    with export.readonly(saved) as read, pytest.raises(sqlite3.OperationalError, match="readonly"):
        read.execute("DELETE FROM identities")
    # Snapshot retains eligibility and flags despite later live changes.
    db.execute("UPDATE sessions SET excluded=1")
    db.execute("UPDATE identities SET needs_review=1")
    audit(db, sid, "reject", NOON + 1)
    result = run_export(data, tmp_path / "bundle", saved)
    assert result.exit_code == 0, result.output
    rows, meta = read_bundle(tmp_path / "bundle")
    assert rows[0]["excluded"] == 0 and meta["eligibility"][sid]["eligible"] is True
    assert saved.read_bytes() == original
    saved.with_name("snapshot.json").unlink()
    assert run_export(data, tmp_path / "missing", saved).exit_code != 0
    assert not (tmp_path / "missing").exists()
    missing_db = tmp_path / "missing.sqlite3"
    assert run_export(data, tmp_path / "no-db", missing_db).exit_code != 0
    assert not missing_db.exists()


@pytest.mark.parametrize("offset,closed", [(-0.000001, False), (0, True), (0.000001, True)])
def test_closure_and_purge_guard(data, tmp_path, monkeypatch, offset, closed):
    runner, db, _ = data
    sid = add_answer(db)
    identify(db, sid)
    refused = runner.invoke(args=["purge-identities", "--yes"])
    assert refused.exit_code != 0
    assert db.execute("SELECT COUNT(*) FROM identities").fetchone()[0] == 1
    monkeypatch.setattr(export.time, "time", lambda: CLOSURE + offset)
    out = tmp_path / "bundle"
    result = run_export(data, out)
    assert result.exit_code == 0, result.output
    assert read_bundle(out)[1]["collection_closed"] is closed
    frozen = export.metadata(db)
    if closed:
        for key, filename in [("answers", "answers.jsonl"), ("metadata", "metadata.json")]:
            assert frozen[f"final_export_{key}_sha256"] == export.sha256(
                (out / filename).read_bytes()
            )
    else:
        assert "final_export_answers_sha256" not in frozen
    assert (runner.invoke(args=["purge-identities", "--yes"]).exit_code == 0) is closed


def test_config_snapshot_exact_bytes_and_mismatch_refusal(data, app, tmp_path):
    runner, db, _ = data
    file = tmp_path / "config.json"
    result = runner.invoke(args=["config-snapshot", "--output", str(file)])
    assert result.exit_code == 0, result.output
    assert file.read_bytes() == export.canonical_bytes(configuration_snapshot(app.config))
    assert (
        result.output.strip()
        == export.sha256(file.read_bytes())
        == export.metadata(db)["config_sha256"]
    )
    assert file.stat().st_mode & 0o777 == 0o600
    db.execute("UPDATE metadata SET value=? WHERE key='config_sha256'", ("0" * 64,))
    bad = tmp_path / "bad.json"
    assert runner.invoke(args=["config-snapshot", "--output", str(bad)]).exit_code != 0
    assert not bad.exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "UPDATE answers SET path='{}'",
        "UPDATE answers SET label='contradictory'",
        "UPDATE answers SET seconds=999999",
        "UPDATE answers SET package_sha256='bad'",
        "UPDATE assignments SET created=0",
        "UPDATE answers SET surplus=1",
    ],
)
def test_invalid_data_never_publishes_partial_output(data, tmp_path, mutation):
    _, db, _ = data
    add_answer(db)
    db.execute(mutation)
    result = run_export(data, tmp_path / "bundle")
    assert result.exit_code != 0
    assert "Synthetic annotation" not in result.output
    assert not (tmp_path / "bundle").exists()
    assert not list(tmp_path.glob(".private-export-*"))


def test_write_failure_cleans_staging(data, tmp_path, monkeypatch):
    _, db, _ = data
    add_answer(db)
    write = export.private_write

    def fail(path, value):
        if path.name == "metadata.json":
            raise OSError("synthetic disk failure")
        return write(path, value)

    monkeypatch.setattr(export, "private_write", fail)
    assert run_export(data, tmp_path / "bundle").exit_code != 0
    assert not (tmp_path / "bundle").exists()
    assert not list(tmp_path.glob(".private-export-*"))


def test_live_export_pins_one_transaction(data, tmp_path, monkeypatch, app):
    _, db, _ = data
    sid = add_answer(db)
    identify(db, sid)
    build = export.build_export

    def concurrent(read_db, *args):
        assert read_db.in_transaction
        db.execute("UPDATE identities SET needs_review=1")
        db.execute("UPDATE sessions SET excluded=1")
        return build(read_db, *args)

    monkeypatch.setattr(export, "build_export", concurrent)
    assert run_export(data, tmp_path / "bundle").exit_code == 0
    rows, meta = read_bundle(tmp_path / "bundle")
    assert rows[0]["excluded"] == 0
    assert meta["eligibility"][sid]["eligible"] is True


def test_snapshot_backup_times_permissions_and_before_refusal(data, tmp_path, monkeypatch):
    runner, db, _ = data
    sid = add_answer(db)
    identify(db, sid)
    early = tmp_path / "early"
    result = runner.invoke(
        args=["snapshot-db", "--at", export.iso(NOON + 1), "--output", str(early)]
    )
    assert result.exit_code != 0 and not early.exists()
    output = tmp_path / "snapshot"
    result = runner.invoke(args=["snapshot-db", "--at", export.iso(NOON), "--output", str(output)])
    assert result.exit_code == 0, result.output
    sidecar = json.loads((output / "snapshot.json").read_bytes())
    assert sidecar == {
        "snapshot_at": export.iso(NOON),
        "captured_at": export.iso(NOON),
        "taken_at": export.iso(NOON),
        "source": "sqlite-backup",
        "exact_instant": True,
    }
    assert json.loads(result.output) == {
        "snapshot_at": export.iso(NOON),
        "taken_at": export.iso(NOON),
        "sha256": export.sha256((output / "app.sqlite3").read_bytes()),
    }
    assert sid not in result.output and "SECRET_SYNTHETIC" not in result.output
    assert output.stat().st_mode & 0o777 == 0o700
    assert all(file.stat().st_mode & 0o777 == 0o600 for file in output.iterdir())
    with export.readonly(output / "app.sqlite3") as saved:
        assert saved.execute("SELECT COUNT(*) FROM answers").fetchone()[0] == 1
    assert run_export(data, tmp_path / "bundle", output / "app.sqlite3").exit_code == 0


def test_snapshot_concurrent_writer_does_not_change_frozen_state(data, app, tmp_path, monkeypatch):
    runner, db, _ = data
    sid = add_answer(db)
    identify(db, sid)
    original = export.metadata

    def pin_then_write(source):
        result = original(source)
        if source.in_transaction:
            # A separate writer commits while the backup read transaction is open.
            db.execute("UPDATE identities SET needs_review=1")
            db.execute("UPDATE sessions SET excluded=1")
        return result

    monkeypatch.setattr(export, "metadata", pin_then_write)
    output = tmp_path / "snapshot"
    result = runner.invoke(args=["snapshot-db", "--at", export.iso(NOON), "--output", str(output)])
    assert result.exit_code == 0, result.output
    with export.readonly(output / "app.sqlite3") as saved:
        assert saved.execute("SELECT needs_review FROM identities").fetchone()[0] == 0
        assert saved.execute("SELECT excluded FROM sessions").fetchone()[0] == 0
    assert db.execute("SELECT excluded FROM sessions").fetchone()[0] == 1


def test_final_snapshot_keeps_source_readonly_and_records_live_purge_receipt(
    data, tmp_path, monkeypatch
):
    _, db, _ = data
    sid = add_answer(db)
    identify(db, sid)
    path = tmp_path / "saved" / "app.sqlite3"
    backup(db, path, CLOSURE)
    original = path.read_bytes()
    monkeypatch.setattr(export.time, "time", lambda: CLOSURE + 60)
    assert run_export(data, tmp_path / "bundle", path).exit_code == 0
    assert path.read_bytes() == original
    assert "final_export_answers_sha256" in export.metadata(db)


@pytest.mark.parametrize("change", ["hash", "reference", "secret", "naive", "future"])
def test_lock_refusals_without_private_error_values(data, tmp_path, change):
    _, db, file = data
    add_answer(db)
    lock = json.loads(file.read_bytes())
    if change == "hash":
        lock["site_configuration_sha256"] = "0" * 64
    elif change == "reference":
        lock["reference_revision_sha256"] = "0" * 64
    elif change == "secret":
        lock["configuration_snapshot"]["nested"] = {"api_key": "DO_NOT_LOG_THIS"}
    elif change == "naive":
        lock["locked_at"] = "2026-11-15T12:00:00"
    else:
        lock["locked_at"] = export.iso(NOON + 1)
    file.write_bytes(export.json_bytes(lock))
    result = run_export(data, tmp_path / "bundle")
    assert result.exit_code != 0
    assert "DO_NOT_LOG_THIS" not in result.output
    assert not (tmp_path / "bundle").exists()


def test_future_identity_confirmation_is_pending(data, tmp_path):
    _, db, _ = data
    sid = add_answer(db)
    identify(db, sid, updated=NOON + 1)
    assert run_export(data, tmp_path / "bundle").exit_code == 0
    assert read_bundle(tmp_path / "bundle")[1]["eligibility"][sid] == {
        "eligible": None,
        "confirmed_at": None,
        "basis": "pending",
    }


def test_operator_factory_exports_backup_without_opening_or_creating_live_db(data, app, tmp_path):
    _, db, lock = data
    add_answer(db)
    saved = tmp_path / "saved" / "app.sqlite3"
    backup(db, saved)
    missing_live = tmp_path / "never-opened.sqlite3"
    operator = export.create_operator_app({**app.config, "DATABASE_PATH": str(missing_live)})
    result = run_export((operator.test_cli_runner(), db, lock), tmp_path / "bundle", saved)
    assert result.exit_code == 0, result.output
    assert not missing_live.exists()
    assert not list(tmp_path.glob("never-opened.sqlite3*"))


@pytest.mark.parametrize("value,expected", [("-3", "other"), ("+3", "3"), ("3.5", "other")])
def test_signed_or_decimal_year(value, expected):
    assert export.year_bucket(value) == expected


def test_late_snapshot_keeps_cutoff_only_when_nothing_exported_changed(data, tmp_path, monkeypatch):
    runner, db, _ = data
    sid = add_answer(db)

    def capture(name, now):
        monkeypatch.setattr(export.time, "time", lambda: now)
        result = runner.invoke(
            args=["snapshot-db", "--at", export.iso(NOON), "--output", str(tmp_path / name)]
        )
        assert result.exit_code == 0, result.output
        return json.loads((tmp_path / name / "snapshot.json").read_bytes())

    # A few seconds of service start-up with no recorded change: the cutoff holds exactly.
    quiet = capture("quiet", NOON + 60)
    assert quiet["snapshot_at"] == export.iso(NOON) and quiet["exact_instant"]
    assert quiet["captured_at"] == export.iso(NOON + 60)
    # Too late to vouch for the cutoff: report the true capture time.
    late = capture("late", NOON + export.EXACT_INSTANT_SECONDS + 1)
    assert late["snapshot_at"] == late["captured_at"] and not late["exact_instant"]
    # A flag or eligibility change after the cutoff: the true capture time again.
    db.execute(
        "INSERT INTO audit(session_id,action,reason,created) VALUES(?,?,?,?)",
        (sid, "exclude", "synthetic", NOON + 1),
    )
    changed = capture("changed", NOON + 60)
    assert changed["snapshot_at"] == export.iso(NOON + 60) and not changed["exact_instant"]
    db.execute("DELETE FROM audit")
    identify(db, sid)
    db.execute("UPDATE identities SET updated=?", (NOON + 1,))
    edited = capture("edited", NOON + 60)
    assert edited["snapshot_at"] == export.iso(NOON + 60) and not edited["exact_instant"]


def test_missing_live_db_does_not_get_created_for_final_receipt(data, app, tmp_path, monkeypatch):
    _, db, lock = data
    add_answer(db)
    saved = tmp_path / "saved" / "app.sqlite3"
    backup(db, saved, CLOSURE)
    missing_live = tmp_path / "never-created.sqlite3"
    operator = export.create_operator_app({**app.config, "DATABASE_PATH": str(missing_live)})
    monkeypatch.setattr(export.time, "time", lambda: CLOSURE + 60)
    result = run_export((operator.test_cli_runner(), db, lock), tmp_path / "bundle", saved)
    assert result.exit_code != 0
    assert not missing_live.exists()
    # The complete validated private export survives a receipt failure.
    rows, meta = read_bundle(tmp_path / "bundle")
    assert len(rows) == 1 and meta["collection_closed"]


@pytest.mark.parametrize("label", export.engine.LABELS)
def test_native_export_derivation_parity(data, tmp_path, label):
    runner, db, _ = data
    add_answer(db)
    derived = validate_path(make_path(label), "Synthetic annotation rationale")
    for field, value in derived.items():
        if isinstance(value, dict):
            value = json.dumps(value)
        db.execute(f"UPDATE answers SET {field}=?", (value,))
    ordinary = tmp_path / "ordinary"
    assert runner.invoke(args=["export-answers", "--output", str(ordinary)]).exit_code == 0
    output = tmp_path / "bundle"
    assert run_export(data, output).exit_code == 0
    old = json.loads((ordinary / "answers.jsonl").read_bytes())
    new = read_bundle(output)[0][0]
    assert old.keys() == new.keys() and len(new) == 25
    for key in new:
        if key.endswith("_at_utc"):
            assert int(export.epoch(new[key])) == export.epoch(old[key])
        else:
            assert old[key] == new[key]


def test_empty_export_and_instrument_bytes_unchanged(data, app, tmp_path):
    from app.config import ROOT

    assert export.instrument_bytes(app.config) == (ROOT / "docs/instrument.json").read_bytes()
    assert run_export(data, tmp_path / "bundle").exit_code == 0
    rows, meta = read_bundle(tmp_path / "bundle")
    assert rows == [] and meta["eligibility"] == {}
    assert meta["demographics"]["sessions"] == 0


def test_submicrosecond_epochs_do_not_round_across_cutoff_or_closure(data, tmp_path, monkeypatch):
    import math

    _, db, _ = data
    cutoff = math.nextafter(CLOSURE, -math.inf)
    add_answer(db, submitted=cutoff)
    monkeypatch.setattr(export.time, "time", lambda: cutoff)
    result = run_export(data, tmp_path / "bundle")
    assert result.exit_code == 0, result.output
    rows, meta = read_bundle(tmp_path / "bundle")
    assert not meta["collection_closed"]
    assert export.epoch(meta["snapshot_at"]) < CLOSURE
    assert rows[0]["submitted_at_utc"] == meta["snapshot_at"] == meta["exported_at"]
    assert rows[0]["submitted_at_utc"].endswith("59.999999+00:00")


def test_open_ended_collection_is_never_closed_without_a_closure_instant(
    data, tmp_path, monkeypatch
):
    runner, db, _ = data
    sid = add_answer(db)
    identify(db, sid)
    monkeypatch.setattr(export.time, "time", lambda: CLOSURE + 30 * 86400)
    out = tmp_path / "bundle"
    result = run_export(data, out, closed_at=None)
    assert result.exit_code == 0, result.output
    assert read_bundle(out)[1]["collection_closed"] is False
    assert "final_export_answers_sha256" not in export.metadata(db)
    assert runner.invoke(args=["purge-identities", "--yes"]).exit_code != 0
