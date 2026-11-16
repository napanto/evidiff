# SPDX-License-Identifier: AGPL-3.0-only
"""Package rebase and amended programmes, on synthetic data only."""

import hashlib
import json
from pathlib import Path

import test_private_export
from test_private_export import NOON, add_answer, identify, read_bundle, run_export
from test_web import get, post

from app import engine
from app import private_export as export
from app.package import canonical_hash

data = test_private_export.data  # the export fixture, reused


def new_package(tmp_path, cfg, count=6, offset=5000):
    source = Path(cfg["PAIR_FILE"])
    items = [json.loads(line) for line in source.read_text().splitlines() if line.strip()][:count]
    old_ids = [item["item_id"] for item in items]
    for item in items:
        item["item_id"] = "v2-pair-" + str(int(item["item_id"].rsplit("-", 1)[1]) + offset)
    payload = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items).encode()
    manifest = json.loads(source.with_suffix(".manifest.json").read_text())
    manifest.update(
        file_sha256=hashlib.sha256(payload).hexdigest(),
        package_sha256=canonical_hash(items),
        item_count=len(items),
        supersedes={item["item_id"]: old for item, old in zip(items, old_ids, strict=True)},
    )
    path = tmp_path / "rebased.jsonl"
    path.write_bytes(payload)
    path.with_suffix(".manifest.json").write_text(json.dumps(manifest))
    return path, [item["item_id"] for item in items], old_ids


def move_answer(db, sid, item_id):
    db.execute("UPDATE answers SET item_id=? WHERE session_id=?", (item_id, sid))
    db.execute("UPDATE assignments SET item_id=? WHERE session_id=?", (item_id, sid))


def test_rebase_keeps_work_and_export_holds_only_live_reads(data, app, tmp_path):
    runner, db, _ = data
    config = export.metadata(db)["config_sha256"]
    first = add_answer(db)
    retired_item = db.execute(
        "SELECT item_id FROM answers WHERE session_id=?", (first,)
    ).fetchone()[0]
    path, new_ids, old_ids = new_package(tmp_path, app.config)
    move_answer(db, first, old_ids[0])
    result = runner.invoke(args=["rebase-package", str(path), "--reason", "synthetic rebase"])
    assert result.exit_code == 0, result.output
    assert retired_item and engine.superseded(db)[new_ids[0]] == old_ids[0]
    live = {r[0] for r in db.execute("SELECT id FROM items WHERE retired=0")}
    assert live == set(new_ids)
    # The reader of a retired pair is offered neither it nor the pair that supersedes it.
    offered = {slot[0] for slot in engine.free_slots(db, app.config, first)}
    assert offered and new_ids[0] not in offered and not offered & set(old_ids)
    # Its valid read stays in both terms of the study meter.
    progress = engine.study_progress(db, app.config)
    assert progress["valid_reads"] == 1 and progress["total_pairs"] == len(new_ids)
    assert progress["required_reads_so_far"] == 1 + len(new_ids) * app.config["INITIAL_READS"]
    # Payment records are untouched; the configuration is unchanged.
    assert db.execute("SELECT paid FROM answers WHERE session_id=?", (first,)).fetchone()[0] == 1
    assert export.metadata(db)["config_sha256"] == config
    # A later read on a live pair carries the new package; the export excludes the retired read.
    second = add_answer(db)
    move_answer(db, second, new_ids[1])
    result = run_export(data, tmp_path / "bundle")
    assert result.exit_code == 0, result.output
    rows, meta = read_bundle(tmp_path / "bundle")
    assert [row["item_id"] for row in rows] == [new_ids[1]]
    assert meta["site_pair_package_sha256"] == rows[0]["package_sha256"]
    assert meta["site_configuration_sha256"] == config
    # A second rebase may not reuse live IDs.
    assert runner.invoke(args=["rebase-package", str(path), "--reason", "again"]).exit_code != 0


def test_retire_item_drops_one_unread_pair(data, app):
    runner, db, _ = data
    config = export.metadata(db)["config_sha256"]
    live = [r[0] for r in db.execute("SELECT id FROM items WHERE retired=0 ORDER BY id")]
    before = engine.study_progress(db, app.config)
    result = runner.invoke(args=["retire-item", live[-1], "--reason", "synthetic duplicate"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["live_pairs"] == len(live) - 1
    after = engine.study_progress(db, app.config)
    assert after["total_pairs"] == before["total_pairs"] - 1
    assert after["required_reads_so_far"] < before["required_reads_so_far"]
    sid = add_answer(db)
    offered = {slot[0] for slot in engine.free_slots(db, app.config, sid)}
    assert live[-1] not in offered
    assert export.metadata(db)["config_sha256"] == config
    # Already retired, unknown, or read pairs are refused.
    assert runner.invoke(args=["retire-item", live[-1], "--reason", "again"]).exit_code
    assert runner.invoke(args=["retire-item", "v2-pair-nope", "--reason", "x"]).exit_code
    read = db.execute("SELECT item_id FROM answers WHERE session_id=?", (sid,)).fetchone()[0]
    assert read != live[-1]
    assert runner.invoke(args=["retire-item", read, "--reason", "x"]).exit_code


def test_amended_programme_counts_only_after_activation(data, app, tmp_path, monkeypatch):
    runner, db, _ = data
    config = export.metadata(db)["config_sha256"]
    assert "bme" not in engine.programmes(db, app.config)
    before = add_answer(db)
    identify(db, before, programme="bme", year="laureato", updated=NOON - 10)
    assert export.eligibility(db, before, NOON)[0]["eligible"] is None
    # The fixture freezes the clock at NOON; activate a little earlier.
    monkeypatch.setattr(export.time, "time", lambda: NOON - 100)
    result = runner.invoke(args=["add-programme", "bme", "--reason", "synthetic"])
    monkeypatch.setattr(export.time, "time", lambda: NOON)
    assert result.exit_code == 0, result.output
    activated = engine.amended_programmes(db)["bme"]
    assert "bme" in engine.programmes(db, app.config)
    assert runner.invoke(args=["add-programme", "bme", "--reason", "again"]).exit_code
    # Declared after activation: eligible like a listed programme, in its own bucket.
    state = export.eligibility(db, before, NOON)[0]
    assert state["eligible"] is True and state["basis"] == "adult_unipi_approved_programme"
    early = add_answer(db)
    identify(db, early, programme="bme", year="laureato", updated=activated - 100)
    assert export.eligibility(db, early, NOON)[0]["eligible"] is None
    result = run_export(data, tmp_path / "bundle")
    assert result.exit_code == 0, result.output
    _, meta = read_bundle(tmp_path / "bundle")
    assert meta["demographics"]["programme"] == {"biomedical_engineering": 1}
    assert export.metadata(db)["config_sha256"] == config
    assert db.execute("SELECT action FROM audit WHERE action='add-programme'").fetchall()


def test_finish_form_offers_amended_programme_only_when_admitted(app):
    def finish(client):
        response = post(client, get(client), "/start")
        return post(
            client,
            get(client, "/finish"),
            "/finish",
            first_name="Synthetic",
            last_name="Graduate",
            eligibility="yes",
            programme="bme",
            year="laureato",
            confirm_below="yes",
        ), response

    client = app.test_client()
    assert b'value="bme"' not in get(client, "/finish").data
    assert finish(client)[0].status_code == 400
    assert (
        app.test_cli_runner()
        .invoke(args=["add-programme", "bme", "--reason", "synthetic"])
        .exit_code
        == 0
    )
    client = app.test_client()
    post(client, get(client), "/start")
    page = get(client, "/finish").data
    assert (
        b'value="bme"' in page
        and b"Ingegneria biomedica" in page
        or (b"Biomedical Engineering" in page)
    )
    response = post(
        client,
        get(client, "/finish"),
        "/finish",
        first_name="Synthetic",
        last_name="Graduate",
        eligibility="yes",
        programme="bme",
        year="laureato",
        confirm_below="yes",
    )
    assert response.status_code == 200
    from app.db import connect

    db = connect(app.config)
    row = db.execute("SELECT programme,needs_review FROM identities").fetchone()
    db.close()
    assert tuple(row) == ("bme", 0)
