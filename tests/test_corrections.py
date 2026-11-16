# SPDX-License-Identifier: AGPL-3.0-only
"""Participant corrections recorded in audit, exported next to the answers (synthetic)."""

import json

import pytest
import test_private_export
from test_private_export import NOON, add_answer, read_bundle, run_export

from app import private_export as export
from app.instrument import make_path, validate_path

data = test_private_export.data  # the export fixture, reused


def record(db, sid, answer_id, path, *, created=NOON - 5, supersedes=None, **override):
    answer = db.execute("SELECT * FROM answers WHERE id=?", (answer_id,)).fetchone()
    derived = validate_path(path, answer["rationale"])
    old = (
        export.derived_summary(answer)
        if supersedes is None
        else json.loads(
            db.execute("SELECT reason FROM audit WHERE id=?", (supersedes,)).fetchone()[0]
        )["derived_new"]
    )
    reason = {
        "type": "participant_correction_after_submission",
        "answer_id": answer_id,
        "item_id": answer["item_id"],
        "answers_row_modified": False,
        "source": "Synthetic participant message",
        "disclosure": "Synthetic disclosure",
        "recorded_by": "Synthetic operator",
        "changes": {"q3": {"old": "yes", "new": "no"}},
        "derived_old": old,
        "derived_new": export.derived_summary(derived),
        "derived_with": {"instrument_version": "2.0"},
        "corrected_path": derived["path"],
        **({"supersedes_audit_id": supersedes} if supersedes is not None else {}),
        **override,
    }
    cur = db.execute(
        "INSERT INTO audit(session_id,action,reason,created) VALUES(?,?,?,?)",
        (sid, "participant-correction", json.dumps(reason), created),
    )
    return cur.lastrowid


def one_answer(db):
    sid = add_answer(db)
    return sid, db.execute("SELECT id FROM answers WHERE session_id=?", (sid,)).fetchone()[0]


def test_no_corrections_gives_an_empty_file(data, tmp_path):
    add_answer(data[1])
    result = run_export(data, tmp_path / "bundle")
    assert result.exit_code == 0, result.output
    assert (tmp_path / "bundle" / "corrections.jsonl").read_bytes() == b""
    _, meta = read_bundle(tmp_path / "bundle")
    assert meta["participant_corrections"] == 0


def test_chain_exports_every_entry_and_applies_the_last(data, tmp_path):
    _, db, _ = data
    sid, answer_id = one_answer(db)
    before = dict(db.execute("SELECT * FROM answers WHERE id=?", (answer_id,)).fetchone())
    first = record(db, sid, answer_id, make_path("not_replicated"), created=NOON - 30)
    second = record(
        db, sid, answer_id, make_path("contradictory"), created=NOON - 20, supersedes=first
    )
    record(db, sid, answer_id, make_path("concordant"), created=NOON + 60, supersedes=second)
    result = run_export(data, tmp_path / "bundle")
    assert result.exit_code == 0, result.output
    lines = (tmp_path / "bundle" / "corrections.jsonl").read_text().splitlines()
    rows = [json.loads(line) for line in lines]
    # The entry after the cutoff is left out; the chain keeps both earlier entries.
    assert [r["audit_id"] for r in rows] == [first, second]
    assert [r["applied"] for r in rows] == [False, True]
    assert rows[1]["derived_new"]["label"] == "contradictory"
    assert rows[1]["supersedes_audit_id"] == first
    # Entries without a corrected note keep the submitted one.
    assert {r["corrected_rationale"] for r in rows} == {before["rationale"]}
    answers, meta = read_bundle(tmp_path / "bundle")
    assert meta["participant_corrections"] == 2
    # The answer itself is exported unchanged; payments are untouched.
    assert answers[0]["label"] == before["label"]
    after = dict(db.execute("SELECT * FROM answers WHERE id=?", (answer_id,)).fetchone())
    assert after == before


@pytest.mark.parametrize(
    "mutation",
    [
        "derived_new",
        "other_session",
        "missing_answer",
        "row_modified",
        "branching",
        "wrong_start",
        "rationale_not_text",
        "rationale_too_long",
    ],
)
def test_invalid_corrections_refuse_the_export(data, tmp_path, mutation):
    _, db, _ = data
    sid, answer_id = one_answer(db)
    path = make_path("not_replicated")
    if mutation == "derived_new":
        record(
            db,
            sid,
            answer_id,
            path,
            derived_new={"label": "concordant", "factor": "none", "binary_inconsistent": False},
        )
    elif mutation == "other_session":
        other, _ = one_answer(db)
        record(db, other, answer_id, path)
    elif mutation == "missing_answer":
        audit_id = record(db, sid, answer_id, path)
        reason = json.loads(
            db.execute("SELECT reason FROM audit WHERE id=?", (audit_id,)).fetchone()[0]
        )
        reason["answer_id"] = 999999
        db.execute("UPDATE audit SET reason=? WHERE id=?", (json.dumps(reason), audit_id))
    elif mutation == "row_modified":
        record(db, sid, answer_id, path, answers_row_modified=True)
    elif mutation == "branching":
        first = record(db, sid, answer_id, path, created=NOON - 30)
        record(db, sid, answer_id, path, created=NOON - 20, supersedes=first)
        record(db, sid, answer_id, path, created=NOON - 10, supersedes=first)
    elif mutation == "wrong_start":
        record(
            db,
            sid,
            answer_id,
            path,
            derived_old={"label": "opposite_world", "factor": "x", "binary_inconsistent": True},
        )
    elif mutation == "rationale_not_text":
        record(db, sid, answer_id, path, corrected_rationale=["not", "text"])
    elif mutation == "rationale_too_long":
        record(db, sid, answer_id, path, corrected_rationale="x" * 1501)
    result = run_export(data, tmp_path / "bundle")
    assert result.exit_code != 0
    assert not (tmp_path / "bundle").exists()


def test_record_correction_command_builds_a_valid_chain(data, tmp_path):
    runner, db, _ = data
    _, answer_id = one_answer(db)
    before = dict(db.execute("SELECT * FROM answers WHERE id=?", (answer_id,)).fetchone())
    for number, label in enumerate(("not_replicated", "contradictory"), 1):
        path_file = tmp_path / f"path{number}.json"
        path_file.write_text(json.dumps(make_path(label)))
        result = runner.invoke(
            args=[
                "record-correction",
                "--answer-id",
                str(answer_id),
                "--corrected-path",
                str(path_file),
                "--source",
                "Synthetic message",
                "--disclosure",
                "Synthetic disclosure",
                "--recorded-by",
                "Synthetic operator",
            ]
        )
        assert result.exit_code == 0, result.output
    # The same path again changes nothing and is refused.
    assert (
        runner.invoke(
            args=[
                "record-correction",
                "--answer-id",
                str(answer_id),
                "--corrected-path",
                str(path_file),
                "--source",
                "s",
                "--disclosure",
                "d",
                "--recorded-by",
                "r",
            ]
        ).exit_code
        != 0
    )
    assert dict(db.execute("SELECT * FROM answers WHERE id=?", (answer_id,)).fetchone()) == before
    db.execute("UPDATE audit SET created=? WHERE action='participant-correction'", (NOON - 5,))
    result = run_export(data, tmp_path / "bundle")
    assert result.exit_code == 0, result.output
    rows = [
        json.loads(x) for x in (tmp_path / "bundle" / "corrections.jsonl").read_text().splitlines()
    ]
    assert [r["applied"] for r in rows] == [False, True]
    assert rows[1]["derived_new"]["label"] == "contradictory"
    assert rows[1]["changes_relative_to"].startswith("corrected_path of audit")


def test_chained_entry_may_inherit_the_disclosure(data, tmp_path):
    _, db, _ = data
    sid, answer_id = one_answer(db)
    first = record(db, sid, answer_id, make_path("not_replicated"), created=NOON - 30)
    second = record(
        db, sid, answer_id, make_path("contradictory"), created=NOON - 20, supersedes=first
    )
    reason = json.loads(db.execute("SELECT reason FROM audit WHERE id=?", (second,)).fetchone()[0])
    del reason["disclosure"]
    db.execute("UPDATE audit SET reason=? WHERE id=?", (json.dumps(reason), second))
    result = run_export(data, tmp_path / "bundle")
    assert result.exit_code == 0, result.output
    rows = [
        json.loads(x) for x in (tmp_path / "bundle" / "corrections.jsonl").read_text().splitlines()
    ]
    assert rows[1]["disclosure"] == rows[0]["disclosure"] == "Synthetic disclosure"


def test_corrected_note_is_carried_and_inherited(data, tmp_path):
    runner, db, _ = data
    _, answer_id = one_answer(db)
    answer = db.execute("SELECT * FROM answers WHERE id=?", (answer_id,)).fetchone()
    # A site correction changes the note; a later operator correction keeps it.
    written = export.write_correction(
        db,
        {"PIPELINE_VERSION": "2.0"},
        answer,
        make_path("not_replicated"),
        rationale="  Corrected note  ",
        source=export.SELF_SERVICE_SOURCE,
        disclosure="Synthetic disclosure",
        recorded_by=export.SELF_SERVICE_RECORDED_BY,
        now=NOON - 30,
    )
    assert written["changes"]["rationale"] == {
        "old": "Synthetic annotation rationale",
        "new": "Corrected note",
    }
    path_file = tmp_path / "path.json"
    path_file.write_text(json.dumps(make_path("contradictory")))
    result = runner.invoke(
        args=[
            "record-correction",
            "--answer-id",
            str(answer_id),
            "--corrected-path",
            str(path_file),
            "--source",
            "Synthetic message",
            "--disclosure",
            "Synthetic disclosure",
            "--recorded-by",
            "Synthetic operator",
        ]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["supersedes_audit_id"] == written["audit_id"]
    result = run_export(data, tmp_path / "bundle")
    assert result.exit_code == 0, result.output
    rows = [
        json.loads(x) for x in (tmp_path / "bundle" / "corrections.jsonl").read_text().splitlines()
    ]
    assert [r["corrected_rationale"] for r in rows] == ["Corrected note", "Corrected note"]
    assert "rationale" not in rows[1]["changes"]
    assert rows[1]["applied"] and rows[1]["derived_new"]["label"] == "contradictory"
    # The answer row keeps the submitted note.
    answers, _ = read_bundle(tmp_path / "bundle")
    assert answers[0]["rationale"] == "Synthetic annotation rationale"


def test_a_correction_is_never_dated_before_the_one_it_replaces(data):
    _, db, _ = data
    _, answer_id = one_answer(db)
    answer = db.execute("SELECT * FROM answers WHERE id=?", (answer_id,)).fetchone()
    kwargs = {"source": "s", "disclosure": "d", "recorded_by": "r"}
    cfg = {"PIPELINE_VERSION": "2.0"}
    first = export.write_correction(
        db, cfg, answer, make_path("not_replicated"), now=NOON, **kwargs
    )
    # A clock that steps back must not reorder the chain the export follows.
    second = export.write_correction(
        db, cfg, answer, make_path("contradictory"), now=NOON - 100, **kwargs
    )
    created = dict(db.execute("SELECT id,created FROM audit WHERE action='participant-correction'"))
    assert created[second["audit_id"]] >= created[first["audit_id"]]
    assert second["supersedes_audit_id"] == first["audit_id"]
    assert export.write_correction(db, cfg, answer, make_path("contradictory"), **kwargs) is None
