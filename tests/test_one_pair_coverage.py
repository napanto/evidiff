# SPDX-License-Identifier: AGPL-3.0-only
"""One pair at a time, coverage first.

Synthetic data only. The transition test rebuilds the state left by the block allocation
(blocks of 4 with one open pair, a session on its practice pair, stale sessions) and
switches it the way the deploy does.
"""

import hashlib
import json
import re
import time

import pytest
from conftest import session
from test_engine import answer_slot, submit_path
from test_web import Forms, get, post

from app import create_app, engine
from app.config import ROOT
from app.db import connect, transaction

T = 1_800_000_000.0
STALE = 30 * 60


def arms(db):
    return {
        r["id"]: json.loads(r["data"])["arm"]
        for r in db.execute("SELECT id,data FROM items WHERE retired=0")
    }


def live_like(db):
    """A study-sized package: 13 biomarker, 12 drug and 10 diet pairs."""
    rows = {r["id"]: json.loads(r["data"]) for r in db.execute("SELECT id,data FROM items")}
    by_arm = {}
    for item_id, data in sorted(rows.items()):
        by_arm.setdefault(data["arm"], []).append((item_id, data))
    for arm, extra in (("biomarker", 5), ("drug", 4), ("diet", 2)):
        for n, (item_id, data) in enumerate(by_arm[arm][:extra]):
            clone = {**data, "item_id": f"{item_id}-c{n}"}
            db.execute(
                "INSERT INTO items(id,data,retired) VALUES(?,?,0)",
                (clone["item_id"], json.dumps(clone)),
            )
    return arms(db)


def by_arm(item_arms, arm):
    return sorted(
        (i for i, a in item_arms.items() if a == arm), key=lambda i: engine.coverage_rank(i)
    )


def next_for_new_reader(db, cfg, now=T):
    sid = session(db, now=now)
    got = engine.reserve(db, cfg, sid, now=now)
    assert len(got) == 1
    row = db.execute("SELECT item_id,slot FROM assignments WHERE id=?", got).fetchone()
    return sid, got[0], row["item_id"], row["slot"]


def reads(db, item_id):
    """Valid reads plus reads in progress, as the coverage order counts them."""
    held = db.execute(
        "SELECT COUNT(*) FROM assignments WHERE item_id=? AND state='reserved' AND kind='real'",
        (item_id,),
    ).fetchone()[0]
    return len(engine.votes(db, item_id)) + held


def covered(db, item_arms, arm, at_least):
    return sum(reads(db, i) >= at_least for i, a in item_arms.items() if a == arm)


def test_coverage_order_on_the_live_arm_mix(db, cfg, synthetic):
    with transaction(db):
        item_arms = live_like(db)
        assert [sum(a == x for a in item_arms.values()) for x in ("biomarker", "drug", "diet")] == [
            13,
            12,
            10,
        ]
        bio, drug, diet = (by_arm(item_arms, a) for a in ("biomarker", "drug", "diet"))
        # Biomarker: 4 pairs read once, 2 twice. Drug: 5 once, 2 twice, one of them split.
        for item in bio[:6] + drug[:7]:
            answer_slot(db, cfg, synthetic, item, 1, "concordant", now=T - 100)
        for item in bio[4:6]:
            answer_slot(db, cfg, synthetic, item, 2, "concordant", now=T - 90)
        answer_slot(db, cfg, synthetic, drug[5], 2, "concordant", now=T - 90)
        answer_slot(db, cfg, synthetic, drug[6], 2, "contradictory", now=T - 90)  # needs a third
        assert engine.pair_state(db, drug[6], cfg)["target"] == 3

        # Step 1: diet is the only arm with fewer than 5 pairs read once; hash order.
        first = [next_for_new_reader(db, cfg) for _ in range(5)]
        assert [(item, slot) for _, _, item, slot in first] == [(i, 1) for i in diet[:5]]
        for sid, aid, _, _ in first:
            submit_path(db, cfg, sid, aid, "concordant", 60, synthetic, now=T + 10)

        # Step 2: second reads until every arm has 5 pairs read twice (done or in progress).
        seconds = []
        while any(covered(db, item_arms, a, 2) < 5 for a in ("biomarker", "drug", "diet")):
            _, _, item, slot = next_for_new_reader(db, cfg)
            assert reads(db, item) == 2 and len(engine.votes(db, item)) == 1, item
            seconds.append(item_arms[item])
        assert sorted(seconds) == ["biomarker"] * 3 + ["diet"] * 5 + ["drug"] * 3
        # The arm furthest behind goes first: diet (0 pairs read twice) until it catches up
        # with the others (2), then the arms take turns.
        assert seconds[:2] == ["diet"] * 2
        assert all(seconds[:k].count("diet") >= 2 for k in range(2, len(seconds)))

        # Step 3: the third read of the split pair comes before any new pair.
        _, _, item, slot = next_for_new_reader(db, cfg)
        assert (item, slot) == (drug[6], 3)
        # Step 4: remaining second reads of single-read pairs, then first reads of new pairs.
        rest = [next_for_new_reader(db, cfg)[2] for _ in range(3)]
        assert all(len(engine.votes(db, i)) == 1 for i in rest)
        _, _, item, slot = next_for_new_reader(db, cfg)
        assert slot == 1 and not engine.votes(db, item)
        # Never more than one pair held per session.
        most = db.execute(
            "SELECT MAX(n) FROM (SELECT COUNT(*) n FROM assignments WHERE state='reserved' "
            "GROUP BY session_id)"
        ).fetchone()[0]
        assert most == 1


def test_ties_follow_the_fixed_hash_order(db, cfg):
    with transaction(db):
        item_arms = arms(db)
        expected = sorted(item_arms, key=engine.coverage_rank)
        assert (
            engine.coverage_rank("x")
            == hashlib.sha256(b"metabolic-evidence-coverage-20261115:x").hexdigest()
        )
        # All arms empty and equal: first reads follow the hash order across arms,
        # moving to the arm furthest behind after each assignment.
        got = [next_for_new_reader(db, cfg)[2] for _ in range(3)]
        assert got[0] == expected[0]
        assert len({item_arms[i] for i in got}) == 3


def test_one_pair_per_session_and_never_the_same_pair_twice(db, cfg, synthetic):
    with transaction(db):
        sid = session(db, now=T)
        seen = set()
        for n in range(12):
            got = engine.reserve(db, cfg, sid, now=T + n)
            assert len(got) == 1 and not engine.reserve(db, cfg, sid, now=T + n)
            item = db.execute("SELECT item_id FROM assignments WHERE id=?", got).fetchone()[0]
            assert item not in seen
            seen.add(item)
            submit_path(db, cfg, sid, got[0], "concordant", 60, synthetic, now=T + n)


def only_pair(db):
    item = db.execute("SELECT id FROM items ORDER BY id LIMIT 1").fetchone()[0]
    db.execute("UPDATE items SET retired=1 WHERE id!=?", (item,))
    return item


@pytest.mark.parametrize("first_to_answer", ["late reader", "new reader"])
def test_stale_open_pair_is_taken_over_and_the_late_answer_is_paid(
    db, cfg, synthetic, first_to_answer
):
    with transaction(db):
        item = only_pair(db)
        old = session(db, now=T)
        [held] = engine.reserve(db, cfg, old, now=T)
        new = session(db, now=T + STALE + 1)
        [taken] = engine.reserve(db, cfg, new, now=T + STALE + 1)
        state = dict(db.execute("SELECT id,state FROM assignments").fetchall())
        assert state[held] == "released" and state[taken] == "reserved"
        assert db.execute("SELECT item_id,slot FROM assignments WHERE id=?", (taken,)).fetchone()[
            :
        ] == (item, 1)
        if first_to_answer == "late reader":
            # The slot is still unfilled: the late answer counts and is paid; the new
            # reader's answer is then a paid surplus within 2 hours of receiving it.
            late = submit_path(db, cfg, old, held, "concordant", 60, synthetic, now=T + 3600)
            assert (late["paid"], late["surplus"]) == (1, 0)
            row = submit_path(db, cfg, new, taken, "concordant", 60, synthetic, now=T + 3700)
            assert (row["paid"], row["late_paid"], row["surplus"]) == (0, 1, 1)
        else:
            row = submit_path(db, cfg, new, taken, "concordant", 60, synthetic, now=T + 3600)
            assert row["paid"] == 1
            late = submit_path(db, cfg, old, held, "concordant", 60, synthetic, now=T + 3700)
            assert (late["paid"], late["late_paid"], late["surplus"]) == (0, 1, 1)
        assert len(engine.votes(db, item)) == 1


def test_late_answer_after_two_hours_to_a_filled_slot_is_not_paid(db, cfg, synthetic):
    with transaction(db):
        only_pair(db)
        old = session(db, now=T)
        [held] = engine.reserve(db, cfg, old, now=T)
        new = session(db, now=T + STALE + 1)
        [taken] = engine.reserve(db, cfg, new, now=T + STALE + 1)
        submit_path(db, cfg, new, taken, "concordant", 60, synthetic, now=T + STALE + 60)
        late = submit_path(db, cfg, old, held, "concordant", 60, synthetic, now=T + 7201)
        assert (late["paid"], late["late_paid"], late["surplus"]) == (0, 0, 1)


@pytest.mark.parametrize("activity", ["submission", "action"])
def test_active_sessions_never_lose_their_open_pair(db, cfg, synthetic, activity):
    with transaction(db):
        only_pair(db)
        reader = session(db, now=T)
        [held] = engine.reserve(db, cfg, reader, now=T)
        if activity == "submission":
            db.execute("UPDATE sessions SET last_submission=? WHERE id=?", (T + 1000, reader))
        else:  # e.g. a saved note or the code page: any POST counts as activity
            db.execute(
                "INSERT INTO actions(id,session_id,endpoint,created) VALUES('a1',?,'code',?)",
                (reader, T + 1000),
            )
        for now in (T + STALE + 1, T + 1000 + STALE - 1):
            other = session(db, now=now)
            engine.reserve(db, cfg, other, now=now)
            assert db.execute("SELECT state FROM assignments WHERE id=?", (held,)).fetchone()[
                0
            ] == ("reserved")
        assert engine.release_stale(db, cfg, now=T + 1000 + STALE) == 1


def test_admission_refuses_without_enough_work(db, cfg):
    cfg.update(PRACTICE_ENABLED=True)
    with transaction(db):
        keep = [r[0] for r in db.execute("SELECT id FROM items ORDER BY id LIMIT 4")]
        db.execute(
            f"UPDATE items SET retired=1 WHERE id NOT IN ({','.join('?' * len(keep))})", keep
        )
        sid = session(db, now=T)
        assert engine.reserve(db, cfg, sid, admission=True, now=T) == []
        db.execute("UPDATE items SET retired=0")
        assert len(engine.reserve(db, cfg, sid, admission=True, now=T)) == 1


def practice_app(cfg):
    return create_app({**cfg, "PRACTICE_ENABLED": True})


def label(response):
    found = re.search(r'class="task-label">(?:Pair|Coppia) (\d+)<', response.data.decode())
    return int(found.group(1)) if found else None


def answer_through_practice(client, synthetic, db):
    page = post(client, get(client), "/start")
    page = post(client, page, "/practice-begin")
    sid = db.execute("SELECT id FROM sessions ORDER BY created DESC LIMIT 1").fetchone()[0]
    item = db.execute(
        "SELECT item_id FROM assignments WHERE session_id=? AND kind='practice'", (sid,)
    ).fetchone()[0]
    practice = synthetic[item]
    page = post(client, page, "/answer", label=practice["answer"], factor=practice["factor"])
    return sid, page


@pytest.mark.parametrize("practice", [True, False])
def test_checkpoints_at_the_same_counts_as_with_blocks(cfg, synthetic, practice):
    app = create_app({**cfg, "PRACTICE_ENABLED": practice})
    db = connect(app.config)
    client = app.test_client()
    if practice:
        sid, page = answer_through_practice(client, synthetic, db)
        page = post(client, page, "/practice-next")
        first = app.config["INITIAL_REAL_BATCH"]
    else:
        page = post(client, get(client), "/start")
        sid = db.execute("SELECT id FROM sessions").fetchone()[0]
        first = app.config["MIN_PAYOUT_PAIRS"]
    checkpoints = []
    items = []
    for n in range(1, first + app.config["CONTINUE_BATCH"] + 1):
        assert b'class="answer-form' in page.data, n
        assert label(page) == n + int(practice)  # pair numbers have no gaps
        items.append(
            db.execute(
                "SELECT item_id FROM assignments WHERE session_id=? AND state='reserved'", (sid,)
            ).fetchone()[0]
        )
        page = post(client, page, "/answer", label="concordant")
        assert page.status_code == 200
        if "/more" in Forms(page.data).forms and b'class="answer-form' not in page.data:
            checkpoints.append(n)
            page = post(client, page, "/more")
    assert checkpoints == [first, first + app.config["CONTINUE_BATCH"]]
    assert len(items) == len(set(items))
    db.close()


def legacy_block(db, sid, items, opened_at, answered, synthetic, cfg, start_position=1):
    """Rows the block allocation left: 4 real reads, the first `answered` answered, the next
    one open (started), the rest never opened."""
    ids = []
    for n, item in enumerate(items):
        aid = f"legacy-{sid[:6]}-{n}"
        ids.append(aid)
        db.execute(
            "INSERT INTO assignments(id,session_id,item_id,kind,slot,position,created,started) "
            "VALUES(?,?,?,'real',1,?,?,?)",
            (aid, sid, item, start_position + n, opened_at, opened_at if n <= answered else None),
        )
        if n < answered:
            submit_path(
                db, cfg, sid, aid, "concordant", 60, synthetic, now=opened_at + 60 * (n + 1)
            )
    return ids


def test_switch_from_blocks_keeps_open_pairs_and_checkpoints(cfg, synthetic):
    app = practice_app(cfg)
    db = connect(app.config)
    now = time.time()
    free = iter(sorted(arms(db), key=engine.coverage_rank, reverse=True))

    # Active A: practice done, block of 4, none answered, pair 1 open.
    a = app.test_client()
    sid_a, page = answer_through_practice(a, synthetic, db)
    # Active B: practice done, block of 4, one answered, pair 2 open.
    b = app.test_client()
    sid_b, _ = answer_through_practice(b, synthetic, db)
    # C is on its practice pair.
    c = app.test_client()
    page_c = post(c, get(c), "/start")
    page_c = post(c, page_c, "/practice-begin")
    sid_c = db.execute("SELECT id FROM sessions ORDER BY created DESC LIMIT 1").fetchone()[0]
    with transaction(db):
        # The block code moved A and B to stage work when it reserved their blocks.
        db.execute("UPDATE sessions SET stage='work' WHERE id IN (?,?)", (sid_a, sid_b))
        block_a = legacy_block(
            db, sid_a, [next(free) for _ in range(4)], now - 600, 0, synthetic, cfg
        )
        block_b = legacy_block(
            db, sid_b, [next(free) for _ in range(4)], now - 900, 1, synthetic, cfg
        )
        # D: stale for 3 hours with a block, pair 1 open. E: stale on its practice pair.
        # F: no submission for 40 minutes but a POST 10 minutes ago, pair open.
        d, e, f = (session(db, now=now - 3 * 3600) for _ in range(3))
        block_d = legacy_block(
            db, d, [next(free) for _ in range(4)], now - 3 * 3600, 0, synthetic, cfg
        )
        engine.add_synthetic(db, app.config, e, "practice", 0, now - 3 * 3600)
        engine.activate_next(db, e, now - 3 * 3600)
        [held_f] = legacy_block(db, f, [next(free)], now - 2400, 0, synthetic, cfg)
        db.execute("UPDATE sessions SET last_submission=? WHERE id=?", (now - 2400, f))
        db.execute(
            "INSERT INTO actions(id,session_id,endpoint,created) VALUES('f-note',?,'code',?)",
            (f, now - 600),
        )

    # Pages open before the switch: A on its pair 1 (pair number 2), B on its pair 2 (3).
    page_a = get(a, "/work")
    page_b = get(b, "/work")
    assert (label(page_a), label(page_b)) == (2, 3)

    result = app.test_cli_runner().invoke(args=["release-blocks", "--reason", "synthetic switch"])
    assert result.exit_code == 0, result.output
    counts = json.loads(result.output)
    assert (counts["released_unopened"], counts["released_inactive"]) == (3 + 2 + 3, 1)
    state = dict(db.execute("SELECT id,state FROM assignments").fetchall())
    assert state[block_a[0]] == state[block_b[1]] == state[held_f] == "reserved"
    assert {state[i] for i in block_a[1:] + block_b[2:] + block_d} == {"released"}
    assert (
        db.execute(
            "SELECT state FROM assignments WHERE session_id=? AND kind='practice'", (e,)
        ).fetchone()[0]
        == "reserved"
    )

    # Forms opened before the switch are accepted after it; the next pair follows the new
    # order, never a pair read before, and the checkpoint comes after practice + 4 in total.
    for client, page, sid, done in ((a, page_a, sid_a, 0), (b, page_b, sid_b, 1)):
        seen = {
            r[0] for r in db.execute("SELECT item_id FROM assignments WHERE session_id=?", (sid,))
        }
        for n in range(done + 1, 5):
            page = post(client, page, "/answer", label="concordant")
            assert page.status_code == 200
            if n < 4:
                assert b'class="answer-form' in page.data and label(page) == n + 2
                [(item,)] = db.execute(
                    "SELECT item_id FROM assignments WHERE session_id=? AND state='reserved'",
                    (sid,),
                ).fetchall()
                assert item not in seen
                seen.add(item)
        assert b'class="answer-form' not in page.data and "/more" in Forms(page.data).forms
        answered = db.execute(
            "SELECT COUNT(*) FROM answers WHERE session_id=? AND kind='real'", (sid,)
        ).fetchone()[0]
        assert answered == 4
    # C finishes its practice and reaches the checkpoint after 4 real pairs.
    item = db.execute(
        "SELECT item_id FROM assignments WHERE session_id=? AND kind='practice'", (sid_c,)
    ).fetchone()[0]
    page_c = post(
        c, page_c, "/answer", label=synthetic[item]["answer"], factor=synthetic[item]["factor"]
    )
    page_c = post(c, page_c, "/practice-next")
    for n in range(1, 5):
        assert b'class="answer-form' in page_c.data and label(page_c) == n + 1
        page_c = post(c, page_c, "/answer", label="concordant")
    assert "/more" in Forms(page_c.data).forms
    # Every answer was recorded once; no session ever held two pairs after the switch.
    assert (
        db.execute("SELECT COUNT(*) FROM answers").fetchone()[0]
        == db.execute("SELECT COUNT(DISTINCT assignment_id) FROM answers").fetchone()[0]
    )
    db.close()


def test_rules_describe_one_pair_at_a_time():
    copy = json.loads((ROOT / "content/copy.json").read_text())
    it, en = copy["it"]["rules"][-2], copy["en"]["rules"][-2]
    assert it.startswith("Il sito assegna una coppia alla volta.")
    assert en.startswith("The site assigns one pair at a time.")
    assert "30 minuti" in it and "2 ore" in it and "30 minutes" in en and "2 hours" in en
    text = json.dumps(copy, ensure_ascii=False)
    assert "lavoro riservato" not in text and "reserved work" not in text
    assert "prenotat" not in text and "reserved pairs" not in text
