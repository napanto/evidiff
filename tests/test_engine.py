# SPDX-License-Identifier: AGPL-3.0-only
from concurrent.futures import ThreadPoolExecutor

from conftest import session

from app import engine
from app.db import connect, transaction
from app.instrument import make_path, validate_path


def submit_path(db, cfg, sid, assignment, label, seconds, synthetic, now=None):
    instrument = validate_path(make_path(label))
    return engine.submit(
        db,
        cfg,
        sid,
        assignment,
        instrument["label"],
        instrument["factor"],
        "",
        seconds,
        synthetic,
        now=now,
        instrument=instrument,
    )


def answer_slot(db, cfg, synthetic, item, slot, label, sid=None, now=2000):
    sid = sid or session(db, now)
    assignment = engine.uid()
    db.execute(
        "INSERT INTO assignments(id,session_id,item_id,kind,slot,position,created) VALUES(?,?,?,'real',?,0,?)",
        (assignment, sid, item, slot, now - 5),
    )
    return submit_path(db, cfg, sid, assignment, label, 5, synthetic, now=now)


def test_escalation_and_unique_plurality(db, cfg, synthetic):
    item = db.execute("SELECT id FROM items LIMIT 1").fetchone()[0]
    with transaction(db):
        answer_slot(db, cfg, synthetic, item, 1, "concordant")
        assert engine.pair_state(db, item, cfg)["target"] == 2
        answer_slot(db, cfg, synthetic, item, 2, "contradictory")
        assert engine.pair_state(db, item, cfg)["target"] == 3
        answer_slot(db, cfg, synthetic, item, 3, "not_comparable")
        assert engine.pair_state(db, item, cfg)["target"] == 4
        answer_slot(db, cfg, synthetic, item, 4, "concordant")
        assert engine.pair_state(db, item, cfg)["status"] == "resolved"


def test_four_distinct_unresolved_and_fourth_limit(db, cfg, synthetic):
    ids = [r[0] for r in db.execute("SELECT id FROM items LIMIT 2")]
    with transaction(db):
        for n, label in enumerate(engine.LABELS[:4], 1):
            answer_slot(db, cfg, synthetic, ids[0], n, label)
        assert engine.pair_state(db, ids[0], cfg)["status"] == "unresolved"
        for n, label in enumerate(engine.LABELS[:3], 1):
            answer_slot(db, cfg, synthetic, ids[1], n, label)
        cfg["MAX_FOURTH_PAIRS"] = 0
        assert engine.pair_state(db, ids[1], cfg)["status"] == "unresolved"


def test_same_pair_never_reassigned_and_admission_atomic(db, cfg, synthetic):
    with transaction(db):
        sid = session(db)
        # One pair at a time.
        assert len(engine.reserve(db, cfg, sid, admission=True)) == 1
        assert not engine.reserve(db, cfg, sid)  # it already holds its pair
        for _ in range(10):
            held = db.execute(
                "SELECT id FROM assignments WHERE session_id=? AND state='reserved'", (sid,)
            ).fetchall()
            assert len(held) == 1
            submit_path(db, cfg, sid, held[0][0], "concordant", 25, synthetic)
            engine.reserve(db, cfg, sid)
        assert (
            db.execute(
                "SELECT COUNT(DISTINCT item_id) FROM assignments WHERE session_id=?", (sid,)
            ).fetchone()[0]
            == 11
        )
        cfg["ADMISSION_MIN_READS"] = 100
        cfg["MIN_PAYOUT_PAIRS"] = 100
        other = session(db)
        assert engine.reserve(db, cfg, other, admission=True) == []
        assert (
            db.execute("SELECT COUNT(*) FROM assignments WHERE session_id=?", (other,)).fetchone()[
                0
            ]
            == 0
        )


def test_inactive_session_loses_its_pair_and_its_late_answer_still_counts(db, cfg, synthetic):
    with transaction(db):
        old = session(db, now=100)
        initial = engine.reserve(db, cfg, old, admission=True, now=100)
        assert len(initial) == 1
        # Released after STALE_MINUTES without activity.
        assert engine.release_stale(db, cfg, now=100 + cfg["STALE_MINUTES"] * 60 - 1) == 0
        assert engine.release_stale(db, cfg, now=100 + cfg["STALE_MINUTES"] * 60) == 1
        # The late original answer is still accepted and counted if its slot remains needed.
        result = submit_path(db, cfg, old, initial[0], "concordant", 30, synthetic, now=4001)
        assert result["paid"] == 1


def test_late_surplus_preserved_and_idempotent(db, cfg, synthetic):
    with transaction(db):
        sid = session(db)
        aid = engine.reserve(db, cfg, sid)[0]
        a = db.execute("SELECT * FROM assignments WHERE id=?", (aid,)).fetchone()
        db.execute("UPDATE assignments SET state='released' WHERE id=?", (aid,))
        answer_slot(db, cfg, synthetic, a["item_id"], a["slot"], "concordant")
        result = submit_path(db, cfg, sid, aid, "not_replicated", 30, synthetic)
        assert result["surplus"] and not result["paid"]
        same = submit_path(db, cfg, sid, aid, "contradictory", 30, synthetic)
        assert same["id"] == result["id"]
        assert same["label"] == "not_replicated"


def test_exclusion_replacement_and_reinstatement(db, cfg, synthetic):
    with transaction(db):
        item = db.execute("SELECT id FROM items LIMIT 1").fetchone()[0]
        first = answer_slot(db, cfg, synthetic, item, 1, "concordant")
        answer_slot(db, cfg, synthetic, item, 2, "concordant")
        assert engine.pair_state(db, item, cfg)["status"] == "resolved"
        engine.exclude(db, first["session_id"], "quality check")
        assert engine.pair_state(db, item, cfg)["status"] == "pending"
        replacement = answer_slot(db, cfg, synthetic, item, 1, "contradictory", now=3000)
        assert replacement["replacement"] == 1
        engine.exclude(db, first["session_id"], "reviewed", value=False)
        assert len(engine.votes(db, item)) == 2
        assert engine.ledger(db, cfg)["paid_reads"] == 3
        assert engine.earnings(db, cfg, first["session_id"])["count"] == 1


def test_hidden_controls_threshold_and_goodfaith_pay(db, cfg, synthetic):
    cfg.update(PRACTICE_ENABLED=True, HIDDEN_CONTROLS_ENABLED=True)
    with transaction(db):
        sid = session(db)
        engine.reserve(db, cfg, sid, admission=True)
        first = db.execute(
            "SELECT * FROM assignments WHERE session_id=? ORDER BY position", (sid,)
        ).fetchall()
        # Admission reserves only the practice pair; real pairs and controls follow it.
        assert [a["kind"] for a in first] == ["practice"]
        for _ in range(30):  # one pair at a time until quality control stops the session
            rows = db.execute(
                "SELECT * FROM assignments WHERE session_id=? AND state='reserved' ORDER BY position",
                (sid,),
            ).fetchall()
            for a in rows:
                if a["kind"] == "control":
                    label = next(x for x in engine.LABELS if x != synthetic[a["item_id"]]["answer"])
                else:
                    label = "concordant"
                submit_path(db, cfg, sid, a["id"], label, 20, synthetic)
            if not engine.reserve(db, cfg, sid):
                break
        kinds = db.execute(
            "SELECT kind, position FROM assignments WHERE session_id=?", (sid,)
        ).fetchall()
        assert any(k["kind"] == "control" and k["position"] < 5 for k in kinds)
        s = db.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
        assert s["quality_failed"] and s["excluded"]
        earned = engine.earnings(db, cfg, sid)
        assert earned["count"] >= 5 and earned["payable_cents"] > 0
        assert not engine.reserve(db, cfg, sid)


def test_synthetic_cap_disables_new_practice_and_controls(db, cfg):
    cfg.update(PRACTICE_ENABLED=True, HIDDEN_CONTROLS_ENABLED=True, MAX_SYNTHETIC_SCREENS=1)
    with transaction(db):
        a, b = session(db), session(db)
        engine.reserve(db, cfg, a, admission=True)
        engine.reserve(db, cfg, b, admission=True)
        assert engine.ledger(db, cfg)["synthetic_issued"] == 1
        assert (
            db.execute(
                "SELECT COUNT(*) FROM assignments WHERE session_id=? AND kind!='real'", (b,)
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute("SELECT COUNT(*) FROM assignments WHERE session_id=?", (b,)).fetchone()[0]
            == 1
        )


def test_minimum_payout_and_configured_fixed_fee(db, cfg, synthetic):
    cfg.update(FIXED_FEE_CENTS=200, FIXED_FEE_MIN_PAIRS=5, BUDGET_CAP_CENTS=30000)
    with transaction(db):
        sid = session(db)
        for _ in range(4):
            submit_path(db, cfg, sid, engine.reserve(db, cfg, sid)[0], "concordant", 20, synthetic)
        assert engine.earnings(db, cfg, sid)["payable_cents"] == 0
        submit_path(db, cfg, sid, engine.reserve(db, cfg, sid)[0], "concordant", 20, synthetic)
        earned = engine.earnings(db, cfg, sid)
        assert (
            earned["count"] == 5
            and earned["fixed"]
            and earned["payable_cents"] == 5 * cfg["PRICE_PER_PAIR_CENTS"] + cfg["FIXED_FEE_CENTS"]
        )


def test_concurrent_simulation_caps_closure(db, cfg, synthetic):
    # Real SQLite connections contend under 16 workers; all directions differ,
    # so this exhausts the third-read and fourth-pair allowances.
    # Scale this simulation cap to the actual preview pool; production settings stay unchanged.
    pair_count = db.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    initial_paid = pair_count * cfg["THIRD_READS"] + cfg["MAX_FOURTH_PAIRS"]
    cfg["PAID_READ_CAP"] = initial_paid + cfg["REPLACEMENT_READS"]

    def worker(_):
        conn = connect(cfg)
        try:
            with transaction(conn):
                sid = session(conn)
            for _ in range(20):
                with transaction(conn):
                    engine.reserve(conn, cfg, sid)
                    rows = conn.execute(
                        "SELECT * FROM assignments WHERE session_id=? AND state='reserved'", (sid,)
                    ).fetchall()
                    for a in rows:
                        submit_path(
                            conn,
                            cfg,
                            sid,
                            a["id"],
                            engine.LABELS[a["slot"] - 1],
                            30,
                            synthetic,
                        )
                    l = engine.ledger(conn, cfg)
                    assert l["paid_reads"] <= cfg["PAID_READ_CAP"]
                    assert l["replacement_reads"] <= 16
                    assert l["spend_cents"] <= cfg["BUDGET_CAP_CENTS"]
                    assert (
                        conn.execute(
                            "SELECT COUNT(*) FROM items WHERE fourth_granted=1"
                        ).fetchone()[0]
                        <= 8
                    )
                if not rows:
                    break
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(worker, range(40)))
    assert engine.ledger(db, cfg)["paid_reads"] == initial_paid
    assert engine.closure(db, cfg) == (True, "complete")
    assert db.execute("SELECT COUNT(*) FROM items WHERE fourth_granted=1").fetchone()[0] == 8
    with transaction(db):
        # Exclude enough sessions to open more than 16 replacement needs.
        for row in db.execute("SELECT DISTINCT session_id FROM answers LIMIT 8").fetchall():
            engine.exclude(db, row[0], "simulation replacement")
    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(worker, range(40)))
    assert engine.ledger(db, cfg)["paid_reads"] == cfg["PAID_READ_CAP"]
    assert engine.ledger(db, cfg)["replacement_reads"] == 16
    assert engine.closure(db, cfg) == (True, "paid_cap")
