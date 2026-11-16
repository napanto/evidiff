# SPDX-License-Identifier: AGPL-3.0-only
"""Late payments: synthetic fixtures only; money never changes scientific flags."""

import csv
import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import session
from test_engine import answer_slot, submit_path
from test_web import get, post

from app import engine
from app.config import settings
from app.db import configuration_snapshot, connect, initialize, transaction


def displaced(db, cfg, synthetic, *, resolved=False):
    sid = session(db, now=1000)
    aid = engine.reserve(db, cfg, sid, now=1000)[0]
    a = db.execute("SELECT * FROM assignments WHERE id=?", (aid,)).fetchone()
    db.execute("UPDATE assignments SET state='released' WHERE id=?", (aid,))
    answer_slot(db, cfg, synthetic, a["item_id"], a["slot"], "concordant", now=1100)
    if resolved:
        answer_slot(db, cfg, synthetic, a["item_id"], 2, "concordant", now=1200)
    return sid, aid, a["item_id"]


@pytest.mark.parametrize("delay,expected", [(3600, 1), (7200, 1), (7201, 0)])
@pytest.mark.parametrize("resolved", [False, True])
def test_late_window_preserves_votes_and_is_idempotent(
    db, cfg, synthetic, delay, expected, resolved
):
    with transaction(db):
        sid, aid, item = displaced(db, cfg, synthetic, resolved=resolved)
        votes = [dict(r) for r in engine.votes(db, item)]
        before = engine.ledger(db, cfg)
        row = submit_path(db, cfg, sid, aid, "contradictory", 60, synthetic, now=1000 + delay)
        assert (row["paid"], row["surplus"], row["late_paid"], row["replacement"]) == (
            0,
            1,
            expected,
            0,
        )
        assert [dict(r) for r in engine.votes(db, item)] == votes
        after = engine.ledger(db, cfg)
        assert after["paid_reads"] == before["paid_reads"]
        assert after["replacement_reads"] == before["replacement_reads"]
        assert (
            after["spend_cents"] == before["spend_cents"] + expected * cfg["PRICE_PER_PAIR_CENTS"]
        )
        assert engine.earnings(db, cfg, sid)["count"] == expected
        assert submit_path(db, cfg, sid, aid, "concordant", 10, synthetic, now=99999) == row
        assert engine.ledger(db, cfg) == after


@pytest.mark.parametrize("block", ["excluded", "finished", "manual", "paid_cap", "complete"])
def test_late_payment_refused_after_stop(db, cfg, synthetic, block):
    with transaction(db):
        sid, aid, item = displaced(db, cfg, synthetic, resolved=block == "complete")
        if block in ("excluded", "finished"):
            db.execute(f"UPDATE sessions SET {block}=1 WHERE id=?", (sid,))
        elif block == "manual":
            db.execute("UPDATE metadata SET value='1' WHERE key='manual_closed'")
        elif block == "paid_cap":
            cfg["PAID_READ_CAP"] = 1
        else:
            db.execute("DELETE FROM items WHERE id!=?", (item,))
        row = submit_path(db, cfg, sid, aid, "concordant", 60, synthetic, now=4600)
        assert (row["paid"], row["surplus"], row["late_paid"]) == (0, 1, 0)
        assert engine.earnings(db, cfg, sid)["cents"] == 0


@pytest.mark.parametrize("fixed_fee", [0, 200])
@pytest.mark.parametrize("headroom_delta,expected", [(-1, 0), (0, 1)])
def test_late_budget_includes_fixed_fee(db, cfg, synthetic, fixed_fee, headroom_delta, expected):
    with transaction(db):
        sid, aid, _ = displaced(db, cfg, synthetic)
        cfg.update(FIXED_FEE_CENTS=fixed_fee, FIXED_FEE_MIN_PAIRS=1)
        before = engine.ledger(db, cfg)["spend_cents"]
        cost = cfg["PRICE_PER_PAIR_CENTS"] + fixed_fee
        cfg["BUDGET_CAP_CENTS"] = before + cost + headroom_delta
        row = submit_path(db, cfg, sid, aid, "concordant", 60, synthetic, now=4600)
        assert row["late_paid"] == expected
        assert engine.earnings(db, cfg, sid)["cents"] == expected * cost
        assert engine.earnings(db, cfg, sid)["fixed"] == bool(expected and fixed_fee)
        assert engine.ledger(db, cfg)["spend_cents"] == before + expected * cost
        assert engine.ledger(db, cfg)["spend_cents"] <= cfg["BUDGET_CAP_CENTS"]


def test_late_spend_constrains_following_real_and_synthetic_answers(db, cfg, synthetic):
    with transaction(db):
        sid, aid, _ = displaced(db, cfg, synthetic)
        cfg["BUDGET_CAP_CENTS"] = (
            engine.ledger(db, cfg)["spend_cents"] + cfg["PRICE_PER_PAIR_CENTS"]
        )
        assert submit_path(db, cfg, sid, aid, "concordant", 60, synthetic, now=4600)["late_paid"]
        next_real = engine.reserve(db, cfg, sid, now=4650)[0]  # one pair at a time
        row = submit_path(db, cfg, sid, next_real, "concordant", 60, synthetic, now=4700)
        assert not row["paid"] and not row["late_paid"]
        assert engine.add_synthetic(db, cfg, sid, "practice", 9, 4700)
        aid = db.execute("SELECT id FROM assignments WHERE kind='practice'").fetchone()[0]
        row = submit_path(db, cfg, sid, aid, "concordant", 60, synthetic, now=4800)
        assert not row["paid"] and not row["late_paid"]
        assert engine.ledger(db, cfg)["spend_cents"] == cfg["BUDGET_CAP_CENTS"]


def test_concurrent_late_answers_cannot_exceed_budget(db, cfg, synthetic):
    with transaction(db):
        pending = [displaced(db, cfg, synthetic) for _ in range(2)]
        cfg["BUDGET_CAP_CENTS"] = (
            engine.ledger(db, cfg)["spend_cents"] + cfg["PRICE_PER_PAIR_CENTS"]
        )

    def submit(entry):
        sid, aid, _ = entry
        connection = connect(cfg)
        try:
            with transaction(connection):
                return submit_path(connection, cfg, sid, aid, "concordant", 60, synthetic, now=4600)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(submit, pending))
    assert sum(r["late_paid"] for r in rows) == 1
    assert engine.ledger(db, cfg)["spend_cents"] == cfg["BUDGET_CAP_CENTS"]


def test_configured_window_is_frozen_and_used(db, cfg, synthetic):
    assert configuration_snapshot(cfg)["LATE_PAYMENT_SECONDS"] == 7200
    with transaction(db):
        sid, aid, _ = displaced(db, cfg, synthetic)
        cfg["LATE_PAYMENT_SECONDS"] = 1800
        row = submit_path(db, cfg, sid, aid, "concordant", 60, synthetic, now=2801)
        assert not row["late_paid"]
    with pytest.raises(RuntimeError, match="Frozen config"):
        initialize(cfg)
    with pytest.raises(ValueError, match="positive"):
        settings({**cfg, "LATE_PAYMENT_SECONDS": -1})


def test_existing_answers_migrate_with_zero_and_reinitialization_preserves_payments(
    db, cfg, synthetic
):
    with transaction(db):
        sid, aid, _ = displaced(db, cfg, synthetic)
    db.execute("ALTER TABLE answers DROP COLUMN late_paid")
    initialize(cfg)
    columns = {r[1]: r for r in db.execute("PRAGMA table_info(answers)")}
    assert columns["late_paid"][2:5] == ("INTEGER", 1, "0")
    assert db.execute("SELECT late_paid FROM answers").fetchone()[0] == 0
    with transaction(db):
        row = submit_path(db, cfg, sid, aid, "concordant", 60, synthetic, now=4600)
    initialize(cfg)
    initialize(cfg)
    assert dict(db.execute("SELECT * FROM answers WHERE id=?", (row["id"],)).fetchone()) == row


def test_header_finish_and_payments_include_late_fifth_pair(app, synthetic, tmp_path):
    client = app.test_client()
    page = post(client, get(client), "/start")
    for _ in range(4):
        page = post(client, page, "/answer", label="concordant")
    db = connect(app.config)
    try:
        with transaction(db):
            a = db.execute("SELECT * FROM assignments WHERE state='reserved' LIMIT 1").fetchone()
            sid = a["session_id"]
            db.execute(
                "UPDATE assignments SET created=?,state='released' WHERE id=?",
                (time.time() - 3600, a["id"]),
            )
            answer_slot(
                db, app.config, synthetic, a["item_id"], a["slot"], "concordant", now=time.time()
            )
        response = post(client, page, "/answer", label="concordant")
        row = db.execute("SELECT * FROM answers WHERE assignment_id=?", (a["id"],)).fetchone()
        assert (row["paid"], row["surplus"], row["late_paid"]) == (0, 1, 1)
        assert "note=saved" in response.request.url
        earned = engine.earnings(db, app.config, sid)
        assert earned["count"] == earned["real"] == 5
        assert earned["payable_cents"] == 500
        finish = get(client, "/finish?lang=en")
        assert b"Pairs done: 5" in finish.data and b"\xe2\x82\xac5.00" in finish.data
        assert b'name="confirm_below"' not in finish.data
        italian = get(client, "/finish?lang=it")
        assert b"Coppie fatte: 5" in italian.data
        final = post(
            client,
            finish,
            "/finish",
            first_name="Synthetic",
            last_name="Student",
            programme="medicine",
            year="3",
            eligibility="yes",
        )
        assert final.status_code == 200 and b"\xe2\x82\xac5.00" in final.data
        assert db.execute("SELECT finished FROM sessions WHERE id=?", (sid,)).fetchone()[0] == 1
        output = tmp_path / "payments.csv"
        result = app.test_cli_runner().invoke(args=["payments", "--output", str(output)])
        assert result.exit_code == 0, result.output
        rows = list(csv.DictReader(output.open()))
        assert len(rows) == 1
        assert rows[0]["paid_screens"] == rows[0]["real_pairs"] == "5"
        assert rows[0]["accrued_eur"] == rows[0]["payable_eur"] == "5.00"
    finally:
        db.close()


def test_rules_include_exact_late_payment_sentence():
    from app.config import ROOT

    copy = json.loads((ROOT / "content/copy.json").read_text())
    # One pair at a time; late answers within 2 hours are paid.
    assert (
        "se la invii comunque entro 2 ore da quando l’hai ricevuta, viene pagata lo stesso."
        in copy["it"]["rules"][-2]
    )
    assert (
        "if you still send it within 2 hours of receiving it, it is paid anyway."
        in copy["en"]["rules"][-2]
    )
