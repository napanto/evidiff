# SPDX-License-Identifier: AGPL-3.0-only
import csv
import json
import re
import time
from pathlib import Path

import click

from . import engine
from .db import connect, purge_ip_fingerprints, transaction


def register(app):
    from .private_export import register as register_private

    register_private(app)

    def pay_amendment_summary(db):
        """The payment amendment as status reports it: never a code, name or session id."""
        amendment = engine.pay_amendment(db)
        if not amendment.get("activated"):
            return {"active": False}
        terms = engine.PAY_AMENDMENT
        return {
            "active": True,
            "activated": amendment["activated"],
            "effective": terms["effective"],
            "real_cents_from_effective": terms["real_cents"],
            "practice_and_earlier_cents": app.config["PRICE_PER_PAIR_CENTS"],
            "personal_cents_from_effective": terms["personal_cents"],
            "personal_sessions": len(amendment.get("personal_sessions", {})),
            "lifted": {
                "BUDGET_CAP_EUR": "not applicable",
                "PAID_READ_CAP": "not applicable",
                "MAX_SYNTHETIC_SCREENS": "not applicable",
                "worst_case": "not applicable",
            },
            "kept": {
                k: "withdrawn (withdraw-fourth-cap)"
                if k == "MAX_FOURTH_PAIRS" and engine.fourth_cap_withdrawn(db).get("activated")
                else app.config[k]
                for k in terms["kept"]
            },
        }

    def fourth_reads_summary(db):
        """The withdrawn fourth-read cap, as status reports it."""
        withdrawn = engine.fourth_cap_withdrawn(db)
        return {
            "cap_withdrawn": bool(withdrawn.get("activated")),
            "activated": withdrawn.get("activated"),
            "pairs_with_fourth_read": db.execute(
                "SELECT COUNT(*) FROM items WHERE fourth_granted=1 AND retired=0"
            ).fetchone()[0],
            "FOURTH_READS": app.config["FOURTH_READS"],
        }

    @app.cli.command("status")
    def status():
        db = connect(app.config)
        try:
            states = [
                engine.pair_state(db, r[0], app.config)["status"]
                for r in db.execute("SELECT id FROM items WHERE retired=0")
            ]
            result = engine.ledger(db, app.config)
            result.update(
                {
                    "closed": engine.closure(db, app.config),
                    "pairs": {k: states.count(k) for k in ("pending", "resolved", "unresolved")},
                    "progress": engine.study_progress(db, app.config),
                    "instrument_version": app.config["INSTRUMENT_VERSION"],
                    "pipeline_version": app.config["PIPELINE_VERSION"],
                    "sessions": db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0],
                    "flags": {
                        k: app.config[k]
                        for k in (
                            "TUTORIAL_ENABLED",
                            "QUALIFICATION_ENABLED",
                            "PRACTICE_ENABLED",
                            "HIDDEN_CONTROLS_ENABLED",
                        )
                    },
                }
            )
            result["preview"] = app.config["PREVIEW_MODE"]
            if not app.config["COMPENSATION_ENABLED"]:
                # No money in an unpaid instance: report reads only.
                result["compensation_enabled"] = False
                for key in (
                    "spend_cents",
                    "worst_case_cents",
                    "worst_case_left_cents",
                    "fixed_fees",
                ):
                    result.pop(key, None)
            summary = pay_amendment_summary(db)
            if summary["active"]:
                result["pay_amendment"] = summary
            if engine.fourth_cap_withdrawn(db).get("activated"):
                result["fourth_reads"] = fourth_reads_summary(db)
            if app.config["PREVIEW_MODE"] and "spend_cents" in result:
                result["simulated_spend_cents"] = result["spend_cents"]
                result["spend_cents"] = 0
            click.echo(json.dumps(result, indent=2))
        finally:
            db.close()

    @app.cli.command("export-answers")
    @click.option(
        "--output",
        type=click.Path(path_type=Path),
        required=True,
        help="Directory for answers.jsonl and answers.csv",
    )
    @click.option(
        "--include-preview",
        is_flag=True,
        help="Include labelled preview rows for timing calibration; never analysis",
    )
    def export_answers(output, include_preview):
        db = connect(app.config)
        try:
            # One read transaction ensures a coherent snapshot while people work.
            db.execute("BEGIN")
            counted = {
                r["id"]
                for item in db.execute("SELECT id FROM items")
                for r in engine.votes(db, item[0])
            }
            rows = db.execute(
                """SELECT a.*, s.excluded,s.quality_failed FROM answers a
                JOIN sessions s ON s.id=a.session_id WHERE a.kind='real' AND (a.preview=0 OR ?) ORDER BY a.id""",
                (int(include_preview),),
            ).fetchall()
            fields = (
                "item_id",
                "read_id",
                "instrument_version",
                "pipeline_version",
                "path",
                "field_problems",
                "relevance",
                "other_detail",
                "binary_inconsistent",
                "package_sha256",
                "config_sha256",
                "session_pseudonym",
                "label",
                "factor",
                "rationale",
                "time_on_item_seconds",
                "submitted_at_utc",
                "assigned_at_utc",
                "paid",
                "replacement",
                "surplus",
                "excluded",
                "quality_failed",
                "counted",
                "preview",
            )
            output.mkdir(parents=True, exist_ok=True)
            with (
                (output / "answers.jsonl").open("w") as jf,
                (output / "answers.csv").open("w", newline="") as cf,
            ):
                writer = csv.DictWriter(cf, fieldnames=fields)
                writer.writeheader()
                for row in rows:
                    assigned = db.execute(
                        "SELECT created FROM assignments WHERE id=?", (row["assignment_id"],)
                    ).fetchone()[0]
                    iso = lambda ts: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))
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
                        "assigned_at_utc": iso(assigned),
                        **{
                            k: row[k]
                            for k in (
                                "paid",
                                "replacement",
                                "surplus",
                                "excluded",
                                "quality_failed",
                            )
                        },
                        "counted": int(row["id"] in counted and not row["preview"]),
                        "preview": row["preview"],
                    }
                    if row["preview"]:
                        data["paid"] = 0
                    jf.write(json.dumps(data, ensure_ascii=False) + "\n")
                    # Prevent spreadsheet formulas in untrusted free text. JSONL preserves exact text.
                    safe = {
                        k: (
                            "'" + str(v)
                            if isinstance(v, str) and v.startswith(("=", "+", "-", "@", "\t", "\r"))
                            else json.dumps(v, ensure_ascii=False)
                            if isinstance(v, (dict, list))
                            else v
                        )
                        for k, v in data.items()
                    }
                    writer.writerow(safe)
            db.commit()
            click.echo(f"Exported {len(rows)} real answers")
        finally:
            db.close()

    @app.cli.command("payments")
    @click.option("--output", type=click.Path(path_type=Path), required=True)
    def payments(output):
        if not app.config["COMPENSATION_ENABLED"]:
            raise click.ClickException("Compensation is disabled for this instance")
        db = connect(app.config)
        try:
            db.execute("BEGIN")
            rows = db.execute(
                "SELECT i.*,s.code_hint FROM identities i JOIN sessions s ON s.id=i.session_id WHERE i.preview=0"
            ).fetchall()
            fields = (
                "session_pseudonym",
                "first_name",
                "last_name",
                "other_programme",
                "payment_exception",
                "programme",
                "year",
                "code_hint",
                "needs_review",
                "real_pairs",
                "paid_screens",
                "fixed_fee_earned",
                "accrued_eur",
                "payable_eur",
            )
            output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            output.touch(mode=0o600, exist_ok=True)
            output.chmod(0o600)
            with output.open("w", newline="") as fp:
                writer = csv.DictWriter(fp, fieldnames=fields)
                writer.writeheader()
                for row in rows:
                    earned = engine.earnings(db, app.config, row["session_id"])
                    data = {
                        k: row[k]
                        for k in (
                            "first_name",
                            "last_name",
                            "other_programme",
                            "programme",
                            "year",
                            "code_hint",
                            "needs_review",
                        )
                    }
                    data.update(
                        session_pseudonym=row["session_id"],
                        payment_exception=earned["payment_exception"],
                        real_pairs=earned["real"],
                        paid_screens=earned["count"],
                        fixed_fee_earned=earned["fixed"],
                        accrued_eur=f"{earned['cents'] / 100:.2f}",
                        payable_eur=f"{earned['payable_cents'] / 100:.2f}",
                    )
                    writer.writerow(
                        {
                            k: (
                                "'" + v
                                if isinstance(v, str)
                                and v.startswith(("=", "+", "-", "@", "\t", "\r"))
                                else v
                            )
                            for k, v in data.items()
                        }
                    )
            db.commit()
            output.chmod(0o600)
            click.echo(f"Wrote {len(rows)} payment records; treat this file as personal data")
        finally:
            db.close()

    for action, value in (("exclude", True), ("include", False)):

        def make_command(action, value):
            @app.cli.command(action)
            @click.argument("session_id")
            @click.option("--reason", required=True)
            def change(session_id, reason):
                db = connect(app.config)
                try:
                    with transaction(db):
                        if not db.execute(
                            "SELECT 1 FROM sessions WHERE id=?", (session_id,)
                        ).fetchone():
                            raise click.ClickException("Unknown session pseudonym")
                        engine.exclude(db, session_id, reason, value)
                    click.echo(f"Session {action}d; recorded payments are unchanged")
                finally:
                    db.close()

        make_command(action, value)

    for action, value in (("close", "1"), ("open", "0")):

        def make_toggle(action, value):
            @app.cli.command(action)
            @click.option("--reason", required=True)
            def toggle(reason):
                db = connect(app.config)
                try:
                    with transaction(db):
                        db.execute(
                            "UPDATE metadata SET value=? WHERE key='manual_closed'", (value,)
                        )
                        db.execute(
                            "INSERT INTO audit(action,reason,created) VALUES(?,?,?)",
                            (action, reason, time.time()),
                        )
                        if value == "1":
                            for row in db.execute("SELECT id FROM sessions").fetchall():
                                engine.record_payment_exception(db, app.config, row[0])
                    click.echo("Manual closure flag updated; automatic closure rules still apply")
                finally:
                    db.close()

        make_toggle(action, value)

    @app.cli.command("rebase-package")
    @click.argument("pair_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
    @click.option("--reason", required=True)
    def rebase_package(pair_file, reason):
        """Retire every current pair and load a new frozen package into this study.

        Sessions, codes, answers and payments stay as they are. Retired pairs are never
        offered again; their valid reads count as resolved work in the study meter.
        Run it with the service stopped, then point PAIR_FILE at the new package.
        """
        from .package import load_pairs

        items, package = load_pairs(
            pair_file, preview=app.config["PREVIEW_MODE"], testing=app.config["TESTING"]
        )
        mapping = package.get("supersedes", {})
        db = connect(app.config)
        try:
            with transaction(db):
                existing = {r[0] for r in db.execute("SELECT id FROM items")}
                if existing & {item["item_id"] for item in items}:
                    raise click.ClickException("New item IDs must not reuse existing IDs")
                if not set(mapping.values()) <= existing or not set(mapping) <= {
                    item["item_id"] for item in items
                }:
                    raise click.ClickException("supersedes must map new IDs to existing IDs")
                released = db.execute(
                    "UPDATE assignments SET state='released' WHERE kind='real' AND state='reserved'"
                ).rowcount
                db.execute("UPDATE items SET retired=1")
                for item in items:
                    db.execute(
                        "INSERT INTO items(id,data,retired) VALUES(?,?,0)",
                        (item["item_id"], json.dumps(item, ensure_ascii=False)),
                    )
                keys = ("pair_sha256", "file_sha256", "package_manifest", "pipeline_version")
                keys += ("package_source_type",)
                previous = {
                    k: db.execute("SELECT value FROM metadata WHERE key=?", (k,)).fetchone()[0]
                    for k in keys
                }
                history = db.execute(
                    "SELECT value FROM metadata WHERE key='package_history'"
                ).fetchone()
                history = json.loads(history[0]) if history else []
                history.append({"retired_at": time.time(), "reason": reason, **previous})
                values = {
                    "pair_sha256": package["package_sha256"],
                    "file_sha256": package["file_sha256"],
                    "package_manifest": json.dumps(package, sort_keys=True, separators=(",", ":")),
                    "pipeline_version": package["pipeline_version"],
                    "package_source_type": package["source_type"],
                    "package_history": json.dumps(history, sort_keys=True),
                }
                for key, value in values.items():
                    db.execute(
                        "INSERT INTO metadata(key,value) VALUES(?,?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (key, value),
                    )
                db.execute(
                    "INSERT INTO audit(action,reason,created) VALUES(?,?,?)",
                    ("rebase-package", f"{reason} [{package['package_sha256']}]", time.time()),
                )
            click.echo(
                json.dumps(
                    {
                        "retired": len(existing),
                        "loaded": len(items),
                        "released_reservations": released,
                        "package_sha256": package["package_sha256"],
                    }
                )
            )
        finally:
            db.close()

    @app.cli.command("retire-item")
    @click.argument("item_id")
    @click.option("--reason", required=True)
    def retire_item(item_id, reason):
        """Retire one live pair that nobody has read or holds (e.g. a duplicate).

        The package file and its hash are unchanged; the pair is no longer offered and
        leaves the study meter. A pair with any answer or reservation is refused.
        """
        db = connect(app.config)
        try:
            with transaction(db):
                row = db.execute("SELECT retired FROM items WHERE id=?", (item_id,)).fetchone()
                if row is None or row[0]:
                    raise click.ClickException("No live pair with this ID")
                if db.execute("SELECT 1 FROM answers WHERE item_id=?", (item_id,)).fetchone():
                    raise click.ClickException("This pair has answers; it cannot be retired")
                if db.execute(
                    "SELECT 1 FROM assignments WHERE item_id=? AND state='reserved'", (item_id,)
                ).fetchone():
                    raise click.ClickException("This pair is reserved; try again later")
                now = time.time()
                db.execute("UPDATE items SET retired=1 WHERE id=?", (item_id,))
                listed = db.execute(
                    "SELECT value FROM metadata WHERE key='retired_items'"
                ).fetchone()
                listed = json.loads(listed[0]) if listed else {}
                listed[item_id] = {"at": now, "reason": reason}
                db.execute(
                    "INSERT INTO metadata(key,value) VALUES('retired_items',?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (json.dumps(listed, sort_keys=True),),
                )
                db.execute(
                    "INSERT INTO audit(action,reason,created) VALUES(?,?,?)",
                    ("retire-item", f"{item_id}: {reason}", now),
                )
                live = db.execute("SELECT COUNT(*) FROM items WHERE retired=0").fetchone()[0]
            click.echo(json.dumps({"retired": item_id, "at": now, "live_pairs": live}))
        finally:
            db.close()

    @app.cli.command("add-programme")
    @click.argument("key", type=click.Choice(sorted(engine.AMENDABLE_PROGRAMMES)))
    @click.option("--reason", required=True)
    def add_programme(key, reason):
        """Admit an amendable programme from now on; the frozen configuration is unchanged."""
        db = connect(app.config)
        try:
            with transaction(db):
                active = engine.amended_programmes(db)
                if key in active:
                    raise click.ClickException("Programme already admitted")
                now = time.time()
                active[key] = now
                db.execute(
                    "INSERT INTO metadata(key,value) VALUES('amended_programmes',?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (json.dumps(active, sort_keys=True),),
                )
                db.execute(
                    "INSERT INTO audit(action,reason,created) VALUES(?,?,?)",
                    ("add-programme", f"{key}: {reason}", now),
                )
            click.echo(json.dumps({"admitted": key, "at": now}))
        finally:
            db.close()

    @app.cli.command("withdraw-fourth-cap")
    @click.option("--reason", required=True)
    def withdraw_fourth_cap(reason):
        """Withdraw the fourth-read cap: every three-way split gets its fourth read from
        now on. MAX_FOURTH_PAIRS stays in the frozen configuration; there is no fifth read."""
        db = connect(app.config)
        try:
            with transaction(db):
                if engine.fourth_cap_withdrawn(db).get("activated"):
                    raise click.ClickException("The fourth-read cap is already withdrawn")
                now = time.time()
                db.execute(
                    "INSERT INTO metadata(key,value) VALUES('fourth_cap_withdrawn',?)",
                    (json.dumps({"activated": now}),),
                )
                db.execute(
                    "INSERT INTO audit(action,reason,created) VALUES(?,?,?)",
                    ("withdraw-fourth-cap", reason, now),
                )
                summary = fourth_reads_summary(db)
            click.echo(json.dumps(summary))
        finally:
            db.close()

    @app.cli.command("release-blocks")
    @click.option("--reason", required=True)
    def release_blocks(reason):
        """Switch to one pair at a time: release every real read reserved but never opened,
        and the reads held by inactive sessions. Open pairs of sessions active in the last
        STALE_MINUTES are kept."""
        db = connect(app.config)
        try:
            with transaction(db):
                now = time.time()
                unopened = engine.release_unopened(db)
                inactive = engine.release_inactive(db, app.config, now)
                db.execute(
                    "INSERT INTO audit(action,reason,created) VALUES(?,?,?)",
                    ("release-blocks", f"unopened={unopened} inactive={inactive}: {reason}", now),
                )
            click.echo(
                json.dumps(
                    {"released_unopened": unopened, "released_inactive": inactive, "at": now}
                )
            )
        finally:
            db.close()

    @app.cli.command("purge-identities")
    @click.option(
        "--yes",
        is_flag=True,
        required=True,
        help="Confirm identities have been paid and may be deleted",
    )
    def purge(yes):
        db = connect(app.config)
        try:
            with transaction(db):
                hashes = dict(
                    db.execute(
                        "SELECT key,value FROM metadata WHERE key IN "
                        "('final_export_answers_sha256','final_export_metadata_sha256')"
                    )
                )
                if len(hashes) != 2 or any(
                    not re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes.values()
                ):
                    raise click.ClickException(
                        "A successful closed export (flask export --closed-at) is required "
                        "before purging identities"
                    )
                db.execute("PRAGMA secure_delete=ON")
                count = db.execute("DELETE FROM identities").rowcount
                db.execute(
                    "INSERT INTO audit(action,reason,created) VALUES(?,?,?)",
                    ("purge-identities", "Operator confirmed payments and retention", time.time()),
                )
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            db.execute("VACUUM")
            click.echo(f"Removed {count} identities. Also expire backups and payment exports.")
        finally:
            db.close()

    @app.cli.command("quality")
    def quality():
        db = connect(app.config)
        try:
            db.execute("BEGIN")
            reports = [
                engine.quality_report(db, app.config, r[0])
                for r in db.execute("SELECT id FROM sessions").fetchall()
            ]
            click.echo(json.dumps(reports, indent=2))
            db.commit()
        finally:
            db.close()

    @app.cli.command("budget")
    @click.option(
        "--set",
        "proposals",
        multiple=True,
        help="Propose KEY=VALUE; repeat for multiple settings. No changes are saved.",
    )
    def budget(proposals):
        import math

        from .config import settings

        candidate = dict(app.config)
        for proposal in proposals:
            key, sep, value = proposal.partition("=")
            if not sep or key not in candidate or key in ("SECRET_KEY", "DATABASE_PATH"):
                raise click.ClickException("Use a documented non-secret configuration KEY=VALUE")
            try:
                parsed = json.loads(value)
            except ValueError:
                parsed = value
            candidate[key] = parsed
        try:
            cfg = settings(candidate, validate_budget=False)
        except (ValueError, TypeError) as error:
            raise click.ClickException(str(error)) from None
        db = connect(app.config)
        try:
            pairs = db.execute("SELECT COUNT(*) FROM items WHERE retired=0").fetchone()[0]
            amendment = pay_amendment_summary(db)
        finally:
            db.close()
        third = pairs * float(cfg["EXPECTED_DISAGREEMENT_RATE"])
        fourth = min(cfg["MAX_FOURTH_PAIRS"], third * float(cfg["EXPECTED_THREE_WAY_RATE"]))
        expected_real = min(
            cfg["PAID_READ_CAP"], 2 * pairs + third + fourth + cfg["EXPECTED_REPLACEMENT_READS"]
        )
        expected_sessions = math.ceil(expected_real / cfg["EXPECTED_PAIRS_PER_SESSION"])
        per_session_synthetic = int(cfg["PRACTICE_ENABLED"])
        if cfg["HIDDEN_CONTROLS_ENABLED"]:
            per_session_synthetic += max(
                1, math.ceil(cfg["EXPECTED_PAIRS_PER_SESSION"] / cfg["CONTROL_INTERVAL"])
            )
        expected_synthetic = min(
            cfg["MAX_SYNTHETIC_SCREENS"], expected_sessions * per_session_synthetic
        )
        expected_screens = expected_real + expected_synthetic
        expected_fixed = (
            min(expected_sessions, int(expected_screens / cfg["FIXED_FEE_MIN_PAIRS"]))
            if cfg["EXPECTED_PAIRS_PER_SESSION"] >= cfg["FIXED_FEE_MIN_PAIRS"]
            else 0
        )
        expected_cents = (
            expected_screens * cfg["PRICE_PER_PAIR_CENTS"] + expected_fixed * cfg["FIXED_FEE_CENTS"]
        )
        enabled_synthetic = (
            cfg["MAX_SYNTHETIC_SCREENS"]
            if cfg["PRACTICE_ENABLED"] or cfg["HIDDEN_CONTROLS_ENABLED"]
            else 0
        )
        click.echo(
            json.dumps(
                {
                    "worst_case_eur": cfg["WORST_CASE_CENTS"] / 100,
                    "budget_cap_eur": cfg["BUDGET_CAP_CENTS"] / 100,
                    "within_budget": cfg["WORST_CASE_CENTS"] <= cfg["BUDGET_CAP_CENTS"],
                    "expected_eur": round(expected_cents / 100, 2),
                    "maximum_paid_sessions_at_minimum": (cfg["PAID_READ_CAP"] + enabled_synthetic)
                    // cfg["MIN_PAYOUT_PAIRS"],
                    "maximum_paid_sessions": cfg["PAID_READ_CAP"] + enabled_synthetic,
                    "below_minimum_exception": "Site-stopped sessions can be paid for accepted tasks below the minimum; per-task cap remains unchanged.",
                    "maximum_fixed_fees": cfg["MAX_FIXED_FEES"],
                    "expected_assumptions": {
                        k: cfg[k]
                        for k in (
                            "EXPECTED_DISAGREEMENT_RATE",
                            "EXPECTED_THREE_WAY_RATE",
                            "EXPECTED_REPLACEMENT_READS",
                            "EXPECTED_PAIRS_PER_SESSION",
                        )
                    },
                    "note": "Planning estimate only, not observed study results; no configuration changed.",
                    **(
                        {
                            "pay_amendment": amendment,
                            "pay_amendment_note": "Active in this database: the money cap, "
                            "PAID_READ_CAP and MAX_SYNTHETIC_SCREENS no longer stop anything, "
                            "and real pairs from the effective time cost more than "
                            "PRICE_PER_PAIR. The worst case and budget figures above describe "
                            "the frozen configuration only and are not applicable.",
                        }
                        if amendment["active"]
                        else {}
                    ),
                },
                indent=2,
            )
        )

    @app.cli.command("feedback")
    @click.option("--output", type=click.Path(path_type=Path), required=True)
    def feedback(output):
        db = connect(app.config)
        try:
            rows = db.execute("SELECT * FROM feedback ORDER BY id").fetchall()
            output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            output.touch(mode=0o600, exist_ok=True)
            output.chmod(0o600)
            with output.open("w") as fp:
                for row in rows:
                    data = {
                        "session_pseudonym": row["session_id"],
                        "screen": row["screen"],
                        "item_id": row["item_id"],
                        "message": row["message"],
                        "preview": row["preview"],
                        "submitted_at_utc": time.strftime(
                            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(row["created"])
                        ),
                    }
                    fp.write(json.dumps(data, ensure_ascii=False) + "\n")
            click.echo(f"Exported {len(rows)} feedback messages")
        finally:
            db.close()

    @app.cli.command("purge-ip-fingerprints")
    def purge_ips():
        """Run hourly via the shipped timer; delete every expired abuse bucket."""
        db = connect(app.config)
        try:
            with transaction(db):
                db.execute("PRAGMA secure_delete=ON")
                count = purge_ip_fingerprints(db)
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            click.echo(f"Deleted {count} expired IP fingerprints")
        finally:
            db.close()

    @app.cli.command("review-eligibility")
    @click.argument("session_id")
    @click.option("--decision", type=click.Choice(["approve", "reject"]), required=True)
    @click.option("--reason", required=True)
    def review_eligibility(session_id, decision, reason):
        """Record an operator's programme check; do not override quality flags."""
        db = connect(app.config)
        try:
            with transaction(db):
                if not reason.strip():
                    raise click.ClickException("A review reason is required")
                changed = db.execute(
                    "UPDATE identities SET needs_review=?,updated=? WHERE session_id=?",
                    (int(decision != "approve"), time.time(), session_id),
                ).rowcount
                if not changed:
                    raise click.ClickException("No identity for that session")
                db.execute(
                    "INSERT INTO audit(session_id,action,reason,created) VALUES(?,?,?,?)",
                    (session_id, "eligibility-" + decision, reason, time.time()),
                )
            click.echo("Eligibility decision saved; quality flags remain unchanged")
        finally:
            db.close()

    @app.cli.command("timing")
    @click.option("--minimum-samples", type=click.IntRange(min=1), default=5, show_default=True)
    def timing(minimum_samples):
        """Summarise completed dev/synthetic tasks before opening a collection."""
        import math
        import statistics

        db = connect(app.config)
        try:
            source = db.execute(
                "SELECT value FROM metadata WHERE key='package_source_type'"
            ).fetchone()[0]
            if source not in ("synthetic", "dev"):
                raise click.ClickException("Timing calibration requires a dev or synthetic package")
            rows = db.execute(
                "SELECT seconds,kind FROM answers WHERE paid=1 AND surplus=0 ORDER BY seconds"
            ).fetchall()
            samples = [r["seconds"] for r in rows]
            median = statistics.median(samples) if samples else None
            p75 = samples[math.ceil(0.75 * len(samples)) - 1] if samples else None
            recommended = math.ceil(p75 * app.config["TARGET_HOURLY_CENTS"] / 3600) if p75 else None
            enough = len(samples) >= minimum_samples
            click.echo(
                json.dumps(
                    {
                        "instrument_version": app.config["INSTRUMENT_VERSION"],
                        "pipeline_version": app.config["PIPELINE_VERSION"],
                        "source_type": source,
                        "preview": app.config["PREVIEW_MODE"],
                        "completed_tasks": len(samples),
                        "median_seconds": median,
                        "p75_seconds": p75,
                        "configured_eur_per_task": app.config["PRICE_PER_PAIR_CENTS"] / 100,
                        "target_eur_per_hour": app.config["TARGET_HOURLY_CENTS"] / 100,
                        "eur_per_hour_at_p75": round(
                            app.config["PRICE_PER_PAIR_CENTS"] * 36 / p75, 2
                        )
                        if p75
                        else None,
                        "minimum_eur_per_task_at_p75": recommended / 100
                        if enough and recommended
                        else None,
                        "enough_samples": enough,
                        "price_meets_target": enough
                        and bool(recommended)
                        and app.config["PRICE_PER_PAIR_CENTS"] >= recommended,
                        "note": "Use careful human work only; timings include pauses. Browser automation is not a pay calibration. Review timings, then set price and budget before starting a fresh production database.",
                    },
                    indent=2,
                )
            )
        finally:
            db.close()

    @app.cli.command("instrument")
    @click.option("--output", type=click.Path(path_type=Path), required=True)
    def instrument_export(output):
        """Export the shared, versioned wording and example paths for the oracle UI."""
        from .private_export import instrument_bytes

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(instrument_bytes(app.config))
        click.echo(
            "Exported versioned wording and paths; examples are not responses to study items"
        )
