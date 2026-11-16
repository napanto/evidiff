# SPDX-License-Identifier: AGPL-3.0-only
import json
import secrets

import pytest
from test_web import Forms, create_app, get, post, snapshot

from app.db import connect


def preview_app(tmp_path):
    return create_app(
        {
            "SECRET_KEY": secrets.token_hex(32),
            "DATABASE_PATH": str(tmp_path / "preview.sqlite3"),
            "BASE_URL": "https://localhost",
            "PREVIEW_MODE": True,
            "PRACTICE_ENABLED": False,
        }
    )


def test_preview_feedback_every_screen_markers_exports_and_payout(tmp_path):
    app = preview_app(tmp_path)
    client = app.test_client()
    before = snapshot(app)
    for page in ("/", "/rules", "/privacy", "/guidelines"):
        response = get(client, page)
        assert b"Preview: answers are not counted or paid" in response.data
        assert "/feedback" in Forms(response.data).forms
    assert snapshot(app) == before
    response = post(client, get(client), "/feedback", message="The comparison question is unclear")
    assert response.status_code == 200
    response = post(client, get(client), "/start")
    response = post(client, response, "/answer", label="concordant", factor="none")
    assert b"\xe2\x82\xac0.00" in response.data
    post(
        client,
        get(client, "/finish"),
        "/finish",
        first_name="Preview",
        last_name="User",
        eligibility="yes",
        confirm_below="yes",
        programme="medicine",
        year="3",
    )
    db = connect(app.config)
    for table in (
        "metadata",
        "items",
        "sessions",
        "identities",
        "assignments",
        "answers",
        "actions",
        "feedback",
    ):
        assert db.execute(f"SELECT COUNT(*) FROM {table} WHERE preview!=1").fetchone()[0] == 0
    runner = app.test_cli_runner()
    assert (
        runner.invoke(args=["export-answers", "--output", str(tmp_path / "default")]).exit_code == 0
    )
    assert (tmp_path / "default/answers.jsonl").read_text() == ""
    assert (
        runner.invoke(
            args=["export-answers", "--include-preview", "--output", str(tmp_path / "timing")]
        ).exit_code
        == 0
    )
    row = json.loads((tmp_path / "timing/answers.jsonl").read_text())
    assert row["preview"] == 1 and row["paid"] == 0 and row["counted"] == 0
    assert runner.invoke(args=["payments", "--output", str(tmp_path / "pay.csv")]).exit_code == 0
    assert "Preview User" not in (tmp_path / "pay.csv").read_text()
    assert (
        runner.invoke(args=["feedback", "--output", str(tmp_path / "feedback.jsonl")]).exit_code
        == 0
    )
    feedback = json.loads((tmp_path / "feedback.jsonl").read_text())
    assert feedback["screen"] == "index" and feedback["preview"] == 1
    assert feedback["message"] == "The comparison question is unclear"
    assert json.loads(runner.invoke(args=["status"]).output)["spend_cents"] == 0
    db.close()


def test_mode_cannot_switch_inside_existing_database(tmp_path):
    app = preview_app(tmp_path)
    with pytest.raises(RuntimeError, match="fresh database"):
        create_app({**app.config, "PREVIEW_MODE": False})


def test_feedback_disabled_in_production(app):
    client = app.test_client()
    assert "/feedback" not in Forms(get(client).data).forms
