# SPDX-License-Identifier: AGPL-3.0-only
"""Withdrawn fourth-read cap: fourth reads without the cap of 8 pairs, no fifth read, and
step 2 counting only pairs that can still resolve. Synthetic data only."""

import hashlib
import json

import pytest
import test_private_export
from conftest import session
from test_engine import answer_slot
from test_one_pair_coverage import arms, by_arm, live_like
from test_private_export import add_answer, run_export
from test_quality import seed_answer
from test_web import get, post

from app import engine
from app.db import configuration_snapshot, connect, transaction

data = test_private_export.data  # the export fixture, reused
T = 1_800_000_000.0
A, B, C, D = "concordant", "contradictory", "not_comparable", "not_replicated"


def withdraw(db):
    """What `flask withdraw-fourth-cap` writes, for engine-level tests."""
    db.execute(
        "INSERT INTO metadata(key,value) VALUES('fourth_cap_withdrawn',?)",
        (json.dumps({"activated": T}),),
    )


def three_way(db, cfg, synthetic, item, now=T):
    for slot, label in enumerate((A, B, C), 1):
        assert answer_slot(db, cfg, synthetic, item, slot, label, now=now + slot)["paid"]


def cap_used(db, cfg, keep):
    """Mark MAX_FOURTH_PAIRS other pairs as already granted a fourth read."""
    others = [r[0] for r in db.execute("SELECT id FROM items WHERE id!=? ORDER BY id", (keep,))]
    for item in others[: cfg["MAX_FOURTH_PAIRS"]]:
        db.execute("UPDATE items SET fourth_granted=1 WHERE id=?", (item,))


def fourth_offered(db, cfg, item):
    return [s for s in engine.free_slots(db, cfg) if s[0] == item and s[1] == 4]


@pytest.mark.parametrize("active", [False, True])
def test_fourth_read_for_every_three_way_split_only_after_activation(db, cfg, synthetic, active):
    with transaction(db):
        item = db.execute("SELECT id FROM items ORDER BY id LIMIT 1").fetchone()[0]
        cap_used(db, cfg, item)
        assert cfg["MAX_FOURTH_PAIRS"] == 8
        three_way(db, cfg, synthetic, item)
        if active:
            withdraw(db)
        state = engine.pair_state(db, item, cfg)
        if active:
            assert (state["status"], state["target"]) == ("pending", 4)
            assert fourth_offered(db, cfg, item)
            row = answer_slot(db, cfg, synthetic, item, 4, A, now=T + 10)
            assert row["paid"] and engine.pair_state(db, item, cfg)["status"] == "resolved"
            assert (
                db.execute("SELECT COUNT(*) FROM items WHERE fourth_granted=1").fetchone()[0]
                == cfg["MAX_FOURTH_PAIRS"]
            )  # granted by reserve(), not answer_slot
        else:  # the old behaviour: the cap is reached, the split stays unresolved
            assert state["status"] == "unresolved" and not fourth_offered(db, cfg, item)
            assert not engine.finally_unresolved(state, cfg)


def test_reserve_grants_fourth_reads_beyond_eight(db, cfg, synthetic):
    with transaction(db):
        withdraw(db)
        items = [r[0] for r in db.execute("SELECT id FROM items ORDER BY id")]
        splits = items[::2][:10]
        # Every other pair is resolved, so steps 1 and 2 are done in every arm.
        for n, item in enumerate(items):
            if item in splits:
                three_way(db, cfg, synthetic, item, now=T + 10 * n)
            else:
                answer_slot(db, cfg, synthetic, item, 1, A, now=T + 10 * n)
                answer_slot(db, cfg, synthetic, item, 2, A, now=T + 10 * n + 1)
        granted = []
        for _ in range(10):
            sid = session(db, now=T + 500)
            got = engine.reserve(db, cfg, sid, now=T + 500)
            row = db.execute("SELECT item_id,slot FROM assignments WHERE id=?", got).fetchone()
            assert row["slot"] == 4  # step 3: fourth reads, more than MAX_FOURTH_PAIRS
            granted.append(row["item_id"])
        assert sorted(granted) == sorted(splits)
        assert db.execute("SELECT COUNT(*) FROM items WHERE fourth_granted=1").fetchone()[0] == 10
        assert cfg["MAX_FOURTH_PAIRS"] == 8


@pytest.mark.parametrize(
    "labels,status",
    [((A, B, A, B), "unresolved"), ((A, B, C, D), "unresolved"), ((A, B, C, A), "resolved")],
)
def test_no_fifth_read_two_two_and_four_way_stay_unresolved(db, cfg, labels, status):
    with transaction(db):
        withdraw(db)
        item = db.execute("SELECT id FROM items ORDER BY id LIMIT 1").fetchone()[0]
        for slot, label in enumerate(labels, 1):
            seed_answer(db, session(db, now=T), item, slot, label)
        state = engine.pair_state(db, item, cfg)
        assert (state["status"], len(state["votes"])) == (status, 4)
        assert engine.finally_unresolved(state, cfg) is (status == "unresolved")
        assert not [s for s in engine.free_slots(db, cfg) if s[0] == item]
        assert cfg["FOURTH_READS"] == 4


def counted_twice(db, cfg, item_arms, arm, active=True):
    """The step-2 measure as free_slots computes it."""
    held = {
        r[0]: r[1]
        for r in db.execute(
            "SELECT item_id,COUNT(*) FROM assignments WHERE state='reserved' AND kind='real' "
            "GROUP BY item_id"
        )
    }
    total = 0
    for item, a in item_arms.items():
        if a != arm:
            continue
        state = engine.pair_state(db, item, cfg)
        reads = len(state["votes"]) + held.get(item, 0)
        total += reads >= 2 and not (active and engine.finally_unresolved(state, cfg))
    return total


@pytest.mark.parametrize("active", [False, True])
def test_final_unresolved_pair_leaves_step_two_and_its_arm_comes_first(db, cfg, synthetic, active):
    with transaction(db):
        item_arms = live_like(db)
        bio, drug, diet = (by_arm(item_arms, a) for a in ("biomarker", "drug", "diet"))
        # Every arm has 5 pairs read twice; diet's are all resolved, biomarker's and drug's
        # too. One more drug pair is read once (a step-4 second read for drug); one more
        # biomarker pair is read once. Every pair of every arm is read at least once.
        for arm in (bio, drug, diet):
            for item in arm[:5]:
                answer_slot(db, cfg, synthetic, item, 1, A, now=T)
                answer_slot(db, cfg, synthetic, item, 2, A, now=T + 1)
            for item in arm[5:]:
                answer_slot(db, cfg, synthetic, item, 1, A, now=T)
        # One biomarker pair ends with four different categories after four reads.
        split = bio[0]
        db.execute("UPDATE answers SET label=? WHERE item_id=? AND slot=1", (B, split))
        db.execute("UPDATE answers SET label=? WHERE item_id=? AND slot=2", (C, split))
        for slot, label in ((3, D), (4, A)):
            seed_answer(db, session(db, now=T), split, slot, label)
        state = engine.pair_state(db, split, cfg)
        assert engine.finally_unresolved(state, cfg) and len(state["votes"]) == 4
        if active:
            withdraw(db)
        assert counted_twice(db, cfg, item_arms, "biomarker", active) == (4 if active else 5)
        order = engine.free_slots(db, cfg)
        step4 = sorted(bio[5:] + drug[5:] + diet[5:], key=engine.coverage_rank)
        if active:
            # Biomarker fell below 5: all its second reads (step 2) come before any second
            # read of the other arms (step 4).
            assert [item_arms[i] for i, *_ in order[: len(bio[5:])]] == ["biomarker"] * len(bio[5:])
            assert all(slot == 2 for _, slot, *_ in order[: len(bio[5:])])
            assert item_arms[order[len(bio[5:])][0]] != "biomarker"
        else:
            # Before activation the split still counts: the second reads of all arms follow
            # the hash order together (step 4 everywhere).
            assert [i for i, *_ in order[: len(step4)]] == step4
            assert {item_arms[i] for i, *_ in order[: len(bio[5:])]} != {"biomarker"}


def test_ordering_on_a_populated_database(db, cfg, synthetic):
    with transaction(db):
        withdraw(db)
        item_arms = live_like(db)
        bio, drug, diet = (by_arm(item_arms, a) for a in ("biomarker", "drug", "diet"))
        # Biomarker: 3 resolved, 1 waiting for a third read, 1 waiting for a fourth read.
        for item in bio[:3]:
            answer_slot(db, cfg, synthetic, item, 1, A, now=T)
            answer_slot(db, cfg, synthetic, item, 2, A, now=T)
        answer_slot(db, cfg, synthetic, bio[3], 1, A, now=T)
        answer_slot(db, cfg, synthetic, bio[3], 2, B, now=T)
        three_way(db, cfg, synthetic, bio[4])
        # Drug: 5 resolved. Diet: 5 read once.
        for item in drug[:5]:
            answer_slot(db, cfg, synthetic, item, 1, A, now=T)
            answer_slot(db, cfg, synthetic, item, 2, A, now=T)
        for item in diet[:5]:
            answer_slot(db, cfg, synthetic, item, 1, A, now=T)
        order = engine.free_slots(db, cfg)
        steps = [
            engine.coverage_priority(
                item_arms[i], len(engine.votes(db, i)), len(engine.votes(db, i)) + 1, cover
            )[0]
            for i, *_ in order
            for cover in [
                {
                    a: [
                        sum(len(engine.votes(db, x)) >= 1 for x, y in item_arms.items() if y == a),
                        counted_twice(db, cfg, item_arms, a),  # activated in this test
                    ]
                    for a in ("biomarker", "drug", "diet")
                }
            ]
        ]
        assert steps == sorted(steps)  # the steps never go backwards
        # Diet's second reads (step 2) first, then the third and fourth reads (step 3).
        assert [item_arms[i] for i, *_ in order[:5]] == ["diet"] * 5
        assert {(i, s) for i, s, *_ in order[5:7]} == {(bio[3], 3), (bio[4], 4)}


def test_switch_keeps_held_pairs_and_accepts_answers_in_flight(cfg, synthetic):
    from app import create_app

    app = create_app({**cfg, "PRACTICE_ENABLED": False})
    db = connect(app.config)
    client = app.test_client()
    page = post(client, get(client), "/start")  # holds one pair, its form open
    sid = db.execute("SELECT id FROM sessions").fetchone()[0]
    held = db.execute(
        "SELECT id FROM assignments WHERE session_id=? AND state='reserved'", (sid,)
    ).fetchall()
    with transaction(db):
        split = db.execute("SELECT id FROM items ORDER BY id DESC LIMIT 1").fetchone()[0]
        cap_used(db, app.config, split)
        three_way(db, app.config, synthetic, split, now=T)
    assert engine.pair_state(db, split, app.config)["status"] == "unresolved"
    result = app.test_cli_runner().invoke(
        args=["withdraw-fourth-cap", "--reason", "synthetic withdrawal"]
    )
    assert result.exit_code == 0, result.output
    summary = json.loads(result.output)
    assert summary["cap_withdrawn"] and summary["pairs_with_fourth_read"] == 8
    again = app.test_cli_runner().invoke(args=["withdraw-fourth-cap", "--reason", "twice"])
    assert again.exit_code != 0 and "already withdrawn" in again.output
    assert (
        db.execute("SELECT state FROM assignments WHERE id=?", (held[0][0],)).fetchone()[0]
        == "reserved"
    )
    # The form opened before the switch is accepted after it, and the next pair follows.
    page = post(client, page, "/answer", label="concordant")
    assert page.status_code == 200
    answered = db.execute("SELECT COUNT(*) FROM answers WHERE session_id=?", (sid,)).fetchone()[0]
    assert answered == 1
    assert engine.pair_state(db, split, app.config)["target"] == 4
    # The fourth read is now offered, and reserve() follows the order.
    assert [s[:2] for s in engine.free_slots(db, app.config) if s[0] == split] == [(split, 4)]
    with transaction(db):
        reader = session(db)
        expected = engine.free_slots(db, app.config, reader)[0][:2]
        got = engine.reserve(db, app.config, reader)
    assert db.execute("SELECT item_id,slot FROM assignments WHERE id=?", got).fetchone()[:] == (
        expected
    )
    # The configuration snapshot is unchanged; status reports the withdrawal honestly.
    metadata = dict(db.execute("SELECT key,value FROM metadata"))
    canonical = json.dumps(
        configuration_snapshot(app.config), sort_keys=True, separators=(",", ":")
    )
    assert metadata["config_json"] == canonical
    assert metadata["config_sha256"] == hashlib.sha256(canonical.encode()).hexdigest()
    status = json.loads(app.test_cli_runner().invoke(args=["status"]).output)
    assert status["fourth_reads"]["cap_withdrawn"] and status["fourth_reads"]["FOURTH_READS"] == 4
    audit = db.execute(
        "SELECT action,reason FROM audit WHERE action='withdraw-fourth-cap'"
    ).fetchall()
    assert [tuple(r) for r in audit] == [("withdraw-fourth-cap", "synthetic withdrawal")]
    db.close()


def test_export_is_unaffected(data, tmp_path):
    _, db, _ = data
    add_answer(db)
    before = tmp_path / "before"
    assert run_export(data, before).exit_code == 0
    with transaction(db):
        withdraw(db)
    after = tmp_path / "after"
    result = run_export(data, after)
    assert result.exit_code == 0, result.output
    for name in ("answers.jsonl", "corrections.jsonl"):
        if (before / name).exists():
            assert (before / name).read_bytes() == (after / name).read_bytes()
    first = json.loads((before / "metadata.json").read_text())
    second = json.loads((after / "metadata.json").read_text())
    assert first == second


def test_arms_helper_reads_the_package(db):
    assert set(arms(db).values()) == {"biomarker", "diet", "drug"}


def test_completion_meter_follows_the_fourth_read_targets(db, cfg, synthetic):
    """The meter and the order read the same pair_state, so both see the withdrawal."""
    with transaction(db):
        items = [r[0] for r in db.execute("SELECT id FROM items ORDER BY id")]
        splits = items[:10]
        for n, item in enumerate(splits):
            three_way(db, cfg, synthetic, item, now=T + 10 * n)
        # Eight splits already hold their fourth read: the cap is reached.
        for item in splits[:8]:
            db.execute("UPDATE items SET fourth_granted=1 WHERE id=?", (item,))
        before = engine.study_progress(db, cfg)
        others = len(items) - len(splits)
        assert before["required_reads_so_far"] == 8 * 4 + 2 * 3 + others * 2
        assert {engine.pair_state(db, i, cfg)["status"] for i in splits[8:]} == {"unresolved"}
        assert not any(s[0] in splits[8:] for s in engine.free_slots(db, cfg))
        withdraw(db)
        after = engine.study_progress(db, cfg)
        # Each split beyond the cap now needs one more read, in the meter and in the order.
        assert after["required_reads_so_far"] == before["required_reads_so_far"] + 2
        assert {(s[0], s[1]) for s in engine.free_slots(db, cfg) if s[0] in splits[8:]} == {
            (i, 4) for i in splits[8:]
        }
        assert after["valid_reads"] == before["valid_reads"] == 30
        assert after["percent"] < before["percent"]
        for key in ("resolved_pairs", "covered_pairs", "total_pairs", "participants"):
            assert after[key] == before[key], key
        assert after["covered_pairs"] == 10 and after["resolved_pairs"] == 0
