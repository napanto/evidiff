# SPDX-License-Identifier: AGPL-3.0-only
import json
import random
from pathlib import Path

from conftest import session

from app import engine
from app.db import transaction
from app.instrument import make_path, validate_path


def seed_answer(db, sid, item, slot, label, seconds=120):
    aid = engine.uid()
    db.execute(
        "INSERT INTO assignments(id,session_id,item_id,kind,slot,position,state,created) VALUES(?,?,?,'real',?,0,'answered',100)",
        (aid, sid, item, slot),
    )
    instrument = validate_path(make_path(label))
    metadata = dict(db.execute("SELECT key,value FROM metadata"))
    db.execute(
        """INSERT INTO answers(assignment_id,session_id,item_id,kind,slot,label,factor,
        rationale,seconds,submitted,paid,instrument_version,pipeline_version,path,
        field_problems,relevance,other_detail,binary_inconsistent,package_sha256,config_sha256)
        VALUES(?,?,?,'real',?,?,?,'',?,200,1,?,?,?,?,?,?,?,?,?)""",
        (
            aid,
            sid,
            item,
            slot,
            instrument["label"],
            instrument["factor"],
            seconds,
            instrument["instrument_version"],
            metadata["pipeline_version"],
            json.dumps(instrument["path"]),
            json.dumps(instrument["field_problems"]),
            instrument["relevance"],
            instrument["other_detail"],
            int(instrument["binary_inconsistent"]),
            metadata["pair_sha256"],
            metadata["config_sha256"],
        ),
    )


def test_quality_simulation_random_fast_and_genuine(db, cfg):
    cfg.update(
        QUALITY_MIN_SHARED_PAIRS=6,
        QUALITY_MAX_AGREEMENTS=1,
        QUALITY_MIN_SPEED_PAIRS=5,
        QUALITY_MIN_MEDIAN_SECONDS=30,
    )
    rng = random.Random(20261113)
    counts = {"genuine": 0, "random": 0, "fast": 0}
    flagged = dict.fromkeys(counts, 0)
    with transaction(db):
        # Ten independent simulated cohorts, each with a slow, consistent
        # reference and disjoint real-pair sets. Labels here are fabricated
        # simulation inputs, not judgments of the frozen study abstracts.
        for trial in range(10):
            reference = session(db)
            people = []
            for kind, number in (("genuine", 4), ("random", 4), ("fast", 4)):
                for participant in range(number):
                    sid = session(db)
                    people.append((sid, kind))
                    for index in range(6):
                        item = f"simulation-{trial}-{kind}-{participant}-{index}"
                        db.execute("INSERT INTO items(id,data) VALUES(?,?)", (item, "{}"))
                        truth = engine.LABELS[index]
                        seed_answer(db, reference, item, 1, truth)
                        label = rng.choice(engine.LABELS) if kind == "random" else truth
                        seed_answer(db, sid, item, 2, label, seconds=8 if kind == "fast" else 120)
            engine.reassess_quality(db, cfg)
            for sid, kind in people:
                report = engine.quality_report(db, cfg, sid)
                counts[kind] += 1
                flagged[kind] += report["flagged"]
        assert flagged["genuine"] == 0
        assert flagged["fast"] == counts["fast"]
        assert flagged["random"] >= counts["random"] // 2
        report = {
            "seed": 20261113,
            "sessions": counts,
            "flagged": flagged,
            "genuine_false_flag_rate": flagged["genuine"] / counts["genuine"],
            "caveat": "Constructed consistent-peer simulation; not an empirical participant error rate. Some random readers pass the prespecified threshold by chance.",
        }
        Path(".local/quality-simulation.json").write_text(json.dumps(report, indent=2) + "\n")


def test_live_speed_rule_and_manual_include(db, cfg, synthetic):
    cfg.update(QUALITY_MIN_SPEED_PAIRS=5, QUALITY_MIN_MEDIAN_SECONDS=30)
    with transaction(db):
        sid = session(db)
        for _ in range(5):  # one pair at a time
            aid = engine.reserve(db, cfg, sid)[0]
            engine.submit(
                db,
                cfg,
                sid,
                aid,
                "concordant",
                "none",
                "",
                10,
                synthetic,
                instrument=validate_path(make_path("concordant")),
            )
        report = engine.quality_report(db, cfg, sid)
        assert report["flagged"] and report["recorded_reason"] == "Live quality: fast_responses"
        assert engine.earnings(db, cfg, sid)["payable_cents"] == 5 * cfg["PRICE_PER_PAIR_CENTS"]
        assert not engine.reserve(db, cfg, sid)
        engine.exclude(db, sid, "Reviewed: accessibility workflow", value=False)
        engine.reassess_quality(db, cfg)
        assert not engine.quality_report(db, cfg, sid)["excluded"]
        assert engine.reserve(db, cfg, sid)


def test_agreement_threshold_patterns_and_progress_readonly(db, cfg):
    cfg.update(QUALITY_MIN_SHARED_PAIRS=6, QUALITY_MIN_SPEED_PAIRS=5)
    with transaction(db):
        a, b, c = session(db), session(db), session(db)
        items = [r[0] for r in db.execute("SELECT id FROM items LIMIT 6")]
        for i, item in enumerate(items):
            seed_answer(db, a, item, 1, "concordant")
            seed_answer(db, b, item, 2, "concordant" if i == 0 else "contradictory")
        report = engine.quality_report(db, cfg, b)
        assert report["shared_pairs"] == 6 and report["agreements"] == 1
        assert "low_peer_agreement" in report["trigger_reasons"]
        assert "same_category_every_pair" in engine.quality_report(db, cfg, a)["patterns"]
        seed_answer(db, c, items[0], 3, "concordant")
        before = db.total_changes
        progress = engine.study_progress(db, cfg)
        assert progress["participants"] == 3 and progress["percent"] < 100
        assert db.total_changes == before
        db.execute("UPDATE metadata SET value='1' WHERE key='manual_closed'")
        closed_progress = engine.study_progress(db, cfg)
        assert closed_progress["closed"]
        assert closed_progress["percent"] == progress["percent"] < 100
        assert closed_progress["covered_pairs"] == 6
        assert closed_progress["resolved_pairs"] < closed_progress["total_pairs"]
