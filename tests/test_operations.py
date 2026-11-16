# SPDX-License-Identifier: AGPL-3.0-only
"""Integration: preserve real paths, comments, identity, and acquired pay."""

import json
import sqlite3
import time

import pytest
from test_web import Forms, create_app, get, post, snapshot

from app.db import connect, transaction
from app.instrument import make_path, validate_path


def identity_fields(**extra):
    return dict(
        first_name="María José",
        last_name="D'Angelo Rossi",
        programme="medicine",
        year="3",
        eligibility="yes",
        **extra,
    )


def start_and_answer(app, **fields):
    client = app.test_client()
    response = post(client, get(client), "/start")
    response = post(client, response, "/answer", label="concordant", factor="none", **fields)
    assert response.status_code == 200
    return client, response


def test_finish_below_minimum_confirmation_is_server_enforced(app):
    client, _ = start_and_answer(app)
    form = Forms(get(client, "/finish").data).forms["/finish"]
    form.update(identity_fields())
    form.pop("confirm_below", None)
    response = client.post(
        "/finish", data=form, base_url="https://localhost", headers={"Origin": "https://localhost"}
    )
    assert response.status_code == 400
    assert snapshot(app)["identities"] == 0
    assert b"no payment is due" in response.data
    response = post(client, response, "/finish", **identity_fields(confirm_below="yes"))
    assert response.status_code == 200 and b'class="message-card final"' in response.data
    db = connect(app.config)
    assert db.execute("SELECT finished FROM sessions").fetchone()[0] == 1
    assert db.execute("SELECT payment_exception FROM sessions").fetchone()[0] == ""
    db.close()


def test_resume_after_finish_is_idempotent_preserves_history_and_upserts_identity(app):
    client, _ = start_and_answer(app)
    response = post(
        client, get(client, "/finish"), "/finish", **identity_fields(confirm_below="yes")
    )
    final = response
    db = connect(app.config)
    original = db.execute("SELECT id,code_hash FROM sessions").fetchone()
    seen = {r[0] for r in db.execute("SELECT item_id FROM assignments")}
    response = post(client, final, "/resume-work")
    assert b'class="answer-form' in response.data
    count = snapshot(app)["assignments"]
    post(client, final, "/resume-work")
    assert snapshot(app)["assignments"] == count
    assert tuple(db.execute("SELECT id,code_hash FROM sessions").fetchone()) == tuple(original)
    assert snapshot(app)["sessions"] == 1
    newly_reserved = {
        r[0] for r in db.execute("SELECT item_id FROM assignments WHERE state='reserved'")
    }
    assert newly_reserved and not newly_reserved.intersection(seen)
    response = post(client, get(client, "/work"), "/answer", label="not_replicated")
    response = post(
        client,
        get(client, "/finish"),
        "/finish",
        **{**identity_fields(confirm_below="yes"), "first_name": "Anna Maria"},
    )
    assert response.status_code == 200
    assert db.execute("SELECT COUNT(*) FROM identities").fetchone()[0] == 1
    assert db.execute("SELECT first_name,last_name FROM identities").fetchone()[0] == "Anna Maria"
    assert db.execute("SELECT COUNT(*) FROM answers").fetchone()[0] == 2
    db.close()


def test_site_stopped_below_threshold_earns_exception_but_voluntary_finish_does_not(app, tmp_path):
    first, _ = start_and_answer(app)
    second, _ = start_and_answer(app)
    post(second, get(second, "/finish"), "/finish", **identity_fields(confirm_below="yes"))
    runner = app.test_cli_runner()
    assert runner.invoke(args=["close", "--reason", "collection operator stop"]).exit_code == 0
    response = post(first, get(first, "/finish"), "/finish", **identity_fields())
    assert response.status_code == 200 and b"Collection has closed" in response.data
    db = connect(app.config)
    exceptions = [r[0] for r in db.execute("SELECT payment_exception FROM sessions")]
    assert exceptions.count("collection_manual") == 1 and exceptions.count("") == 1
    assert runner.invoke(args=["payments", "--output", str(tmp_path / "pay.csv")]).exit_code == 0
    import csv

    rows = list(csv.DictReader((tmp_path / "pay.csv").open()))
    assert sorted(row["payable_eur"] for row in rows) == ["0.00", "1.00"]
    db.close()


def test_preview_comment_and_answer_atomic_retry_and_confirmed_draft(cfg):
    app = create_app({**cfg, "PREVIEW_MODE": True})
    client = app.test_client()
    response = post(client, get(client), "/start")
    assert "/feedback" not in Forms(response.data).forms
    form = Forms(response.data).forms["/answer"]
    form.update(
        path=json.dumps(make_path("concordant")), comment="The number refers to a subgroup."
    )
    kwargs = {
        "data": form,
        "base_url": "https://localhost",
        "headers": {"Origin": "https://localhost"},
    }
    response = client.post("/answer", **kwargs, follow_redirects=True)
    assert response.status_code == 200
    db = connect(app.config)
    answer = db.execute("SELECT * FROM answers").fetchone()
    comment = db.execute("SELECT * FROM feedback").fetchone()
    assert comment["answer_id"] == answer["id"] and comment["item_id"] == answer["item_id"]
    assert f'data-saved-draft="{answer["assignment_id"]}"'.encode() in response.data
    client.post("/answer", **kwargs)
    assert snapshot(app)["answers"] == 1 and snapshot(app)["feedback"] == 1
    assert b'data-saved-draft=""' in get(client, "/work?saved=unsaved").data
    # A failed feedback insert must roll back the answer, slot state and action nonce.
    db.execute(
        "CREATE TRIGGER reject_feedback BEFORE INSERT ON feedback BEGIN SELECT RAISE(ABORT,'test rollback'); END"
    )
    before = snapshot(app)
    with pytest.raises(sqlite3.IntegrityError, match="test rollback"):
        post(client, get(client, "/work"), "/answer", label="concordant", comment="Rollback both")
    assert snapshot(app) == before
    db.close()


def test_eligibility_required_and_other_withheld_until_recorded_approval(app, tmp_path):
    client, _ = start_and_answer(app)
    form = Forms(get(client, "/finish").data).forms["/finish"]
    form.update(identity_fields(confirm_below="yes"))
    form.pop("eligibility", None)
    response = client.post(
        "/finish", data=form, base_url="https://localhost", headers={"Origin": "https://localhost"}
    )
    assert response.status_code == 400 and snapshot(app)["identities"] == 0
    post(
        client,
        get(client, "/finish"),
        "/finish",
        **{
            **identity_fields(confirm_below="yes"),
            "programme": "other",
            "other_programme": "Programme requiring review",
        },
    )
    db = connect(app.config)
    from app import engine

    sid = db.execute("SELECT id FROM sessions").fetchone()[0]
    item = db.execute("SELECT item_id FROM answers").fetchone()[0]
    assert not engine.votes(db, item)
    assert engine.earnings(db, app.config, sid)["payable_cents"] == 0
    runner = app.test_cli_runner()
    result = runner.invoke(
        args=[
            "review-eligibility",
            sid,
            "--decision",
            "approve",
            "--reason",
            "Verified eligible programme",
        ]
    )
    assert result.exit_code == 0, result.output
    assert len(engine.votes(db, item)) == 1
    post(
        client,
        get(client, "/finish"),
        "/finish",
        **{
            **identity_fields(confirm_below="yes"),
            "programme": "other",
            "other_programme": "Programme requiring review",
            "first_name": "Updated name",
        },
    )
    assert db.execute("SELECT needs_review FROM identities").fetchone()[0] == 0
    assert (
        db.execute("SELECT COUNT(*) FROM audit WHERE action='eligibility-approve'").fetchone()[0]
        == 1
    )
    db.close()


def test_export_preserves_full_answer_path_and_provenance_without_names(app, tmp_path):
    client = app.test_client()
    response = post(client, get(client), "/start")
    path = make_path("concordant")
    path["q1"]["b"]["sample_size"] = {"answer": "no", "problems": ["missing_from_extraction"]}
    path["q1_relevance"] = "not_material"
    response = post(
        client, response, "/answer", path=json.dumps(path), label_ignored="contradictory"
    )
    assert response.status_code == 200
    out = tmp_path / "export"
    assert (
        app.test_cli_runner().invoke(args=["export-answers", "--output", str(out)]).exit_code == 0
    )
    data = json.loads((out / "answers.jsonl").read_text())
    assert data["label"] == "concordant" and data["relevance"] == "not_material"
    assert data["instrument_version"] == data["pipeline_version"] == "2.0"
    assert len(data["package_sha256"]) == len(data["config_sha256"]) == 64
    assert data["read_id"] and data["field_problems"]["b"]["sample_size"]["problems"] == [
        "missing_from_extraction"
    ]
    assert validate_path(data["path"])["label"] == data["label"]
    assert not {"first_name", "last_name", "programme"}.intersection(data)


def test_server_rejects_forged_terminal_label_without_path(app):
    client = app.test_client()
    response = post(client, get(client), "/start")
    form = Forms(response.data).forms["/answer"]
    form.update(label="concordant", factor="none", path="{}")
    response = client.post(
        "/answer", data=form, base_url="https://localhost", headers={"Origin": "https://localhost"}
    )
    assert response.status_code == 400 and snapshot(app)["answers"] == 0


def test_hourly_ip_purge_and_readonly_get(app):
    db = connect(app.config)
    now = time.time()
    with transaction(db):
        db.execute("INSERT INTO rate_limits(bucket,count,until) VALUES('expired',3,?)", (now - 1,))
        db.execute(
            "INSERT INTO rate_limits(bucket,count,until) VALUES('current',1,?)", (now + 900,)
        )
    get(app.test_client())
    assert db.execute("SELECT COUNT(*) FROM rate_limits").fetchone()[0] == 2
    result = app.test_cli_runner().invoke(args=["purge-ip-fingerprints"])
    assert result.exit_code == 0 and "Deleted 1" in result.output
    assert [r[0] for r in db.execute("SELECT bucket FROM rate_limits")] == ["current"]
    db.close()


def test_timing_calibration_is_dev_only_and_does_not_change_config(app):
    client = app.test_client()
    response = post(client, get(client), "/start")
    for _ in range(5):
        response = post(client, response, "/answer", label="concordant")
    db = connect(app.config)
    db.execute("UPDATE answers SET seconds=600")
    result = app.test_cli_runner().invoke(args=["timing"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["median_seconds"] == 600 and data["minimum_eur_per_task_at_p75"] == 1.67
    assert data["eur_per_hour_at_p75"] == 6 and not data["price_meets_target"]
    assert app.config["PRICE_PER_PAIR_CENTS"] == 100
    db.execute("UPDATE metadata SET value='production' WHERE key='package_source_type'")
    assert app.test_cli_runner().invoke(args=["timing"]).exit_code != 0
    db.close()


def test_old_schema_database_and_changed_config_rejected(app):
    with pytest.raises(RuntimeError, match="Frozen config"):
        create_app({**app.config, "PRICE_PER_PAIR_EUR": "1.40"})
    db = connect(app.config)
    db.execute("UPDATE metadata SET value='1' WHERE key='schema_version'")
    db.close()
    with pytest.raises(RuntimeError, match="fresh database"):
        create_app(dict(app.config))


def test_crawler_and_text_mining_directives_every_response_and_html(app):
    client = app.test_client()
    for path in (
        "/",
        "/robots.txt",
        "/.well-known/tdmrep.json",
        "/healthz",
        "/missing",
        "/static/app.js",
    ):
        response = get(client, path)
        assert (
            response.headers["X-Robots-Tag"]
            == "noindex, nofollow, noarchive, nosnippet, noimageindex, noai, noimageai"
        )
        assert response.headers["tdm-reservation"] == "1"
    landing = get(client).data.decode()
    assert (
        '<meta name="robots" content="noindex, nofollow, noarchive, nosnippet, noimageindex">'
        in landing
    )
    assert '<meta name="tdm-reservation" content="1">' in landing
    robots = get(client, "/robots.txt").data.decode()
    assert robots.startswith("Content-Signal: search=no, ai-input=no, ai-train=no")
    for agent in ("*", "GPTBot", "ClaudeBot", "Google-Extended", "CCBot"):
        assert f"User-agent: {agent}\nDisallow: /" in robots
    assert get(client, "/.well-known/tdmrep.json").json == [{"location": "/", "tdm-reservation": 1}]


def test_one_proxy_client_ip_ignores_direct_cdn_header(app):
    import hashlib
    import hmac

    client = app.test_client()
    form = Forms(get(client).data).forms["/resume"]
    form["code"] = "incorrect"
    response = client.post(
        "/resume",
        data=form,
        base_url="https://localhost",
        headers={
            "Origin": "https://localhost",
            "X-Forwarded-For": "192.0.2.10",
            "CF-Connecting-IP": "192.0.2.99",
        },
    )
    assert response.status_code == 400
    expected = hmac.new(
        app.config["SECRET_KEY"].encode(), b"rate:192.0.2.10", hashlib.sha256
    ).hexdigest()
    db = connect(app.config)
    assert [row[0] for row in db.execute("SELECT bucket FROM rate_limits")] == [expected]
    db.close()
