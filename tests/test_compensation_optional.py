# SPDX-License-Identifier: AGPL-3.0-only
"""COMPENSATION_ENABLED: off by default, per instance, frozen with the study."""

import json
import secrets
import sqlite3

import pytest

from app import create_app
from app.config import ROOT, settings
from app.db import PAYMENT_SNAPSHOT_KEYS, configuration_snapshot, stored_compensation
from tests.test_web import get, post

MONEY = (
    "€",
    "compens",
    "pagament",
    "pagat",
    "retribu",
    "payment",
    "pay ",
    "Pay ",
    "payable",
    "paid",
    "Pairs done: 1 ·",
)


def base(tmp_path, **extra):
    return {
        "SECRET_KEY": secrets.token_hex(32),
        "DATABASE_PATH": str(tmp_path / "study.sqlite3"),
        "BASE_URL": "https://localhost",
        "TESTING": True,
        "PAIR_FILE": str(ROOT / "content/preview_pairs.jsonl"),
        "PRACTICE_ENABLED": False,
        "HIDDEN_CONTROLS_ENABLED": False,
        "QUALITY_MIN_SHARED_PAIRS": 1000,
        "QUALITY_MIN_SPEED_PAIRS": 1000,
        **extra,
    }


@pytest.mark.unpaid
def test_default_is_off_and_amounts_are_not_needed(tmp_path, monkeypatch):
    monkeypatch.delenv("COMPENSATION_ENABLED")
    cfg = settings(base(tmp_path, BUDGET_CAP_EUR="0", TARGET_HOURLY_EUR="0"))
    assert cfg["COMPENSATION_ENABLED"] is False
    assert cfg["PRICE_PER_PAIR_CENTS"] == cfg["FIXED_FEE_CENTS"] == cfg["WORST_CASE_CENTS"] == 0
    snapshot = configuration_snapshot(cfg)
    assert snapshot["COMPENSATION_ENABLED"] is False
    assert not PAYMENT_SNAPSHOT_KEYS & snapshot.keys()


def test_paid_snapshot_has_the_keys_it_had_before_the_switch(tmp_path):
    cfg = settings(base(tmp_path))
    assert cfg["COMPENSATION_ENABLED"] is True
    snapshot = configuration_snapshot(cfg)
    assert "COMPENSATION_ENABLED" not in snapshot and "CONTACT_EMAIL" not in snapshot
    assert PAYMENT_SNAPSHOT_KEYS <= snapshot.keys()


@pytest.mark.unpaid
def test_unpaid_pages_ask_for_and_show_no_money(tmp_path, monkeypatch):
    monkeypatch.delenv("COMPENSATION_ENABLED")
    app = create_app(base(tmp_path))
    assert app.config["COMPENSATION_ENABLED"] is False
    client = app.test_client()
    pages = ("/", "/rules", "/privacy", "/guidelines")
    for path in (f"{page}?lang={lang}" for page in pages for lang in ("en", "it")):
        body = get(client, path).data.decode()
        assert "pay-callout" not in body and not any(word in body for word in MONEY), path
    response = post(client, get(client), "/start")
    post(client, response, "/answer", label="concordant", factor="none", rationale="A comparison")
    work = get(client, "/work?lang=en").data.decode()
    assert not any(word in work for word in MONEY)
    form = get(client, "/finish?lang=en").data.decode()
    assert 'name="first_name"' not in form and 'name="confirm_below"' not in form
    final = post(
        client, get(client, "/finish"), "/finish", eligibility="yes", programme="medicine", year="3"
    )
    assert final.status_code == 200
    body = final.data.decode()
    assert "final-pay" not in body and not any(word in body for word in MONEY)
    runner = app.test_cli_runner()
    result = runner.invoke(args=["payments", "--output", str(tmp_path / "p.csv")])
    assert result.exit_code != 0 and "disabled" in result.output
    assert not (tmp_path / "p.csv").exists()
    status = json.loads(runner.invoke(args=["status"]).output)
    assert status["compensation_enabled"] is False and "spend_cents" not in status
    db = sqlite3.connect(app.config["DATABASE_PATH"])
    assert db.execute("SELECT first_name,last_name FROM identities").fetchall() == [("", "")]
    db.close()


@pytest.mark.unpaid
def test_an_unpaid_study_cannot_be_switched_to_paid(tmp_path, monkeypatch):
    monkeypatch.delenv("COMPENSATION_ENABLED")
    create_app(base(tmp_path))
    assert stored_compensation(tmp_path / "study.sqlite3") is False
    assert create_app(base(tmp_path)).config["COMPENSATION_ENABLED"] is False
    with pytest.raises(RuntimeError, match="created without compensation"):
        create_app(base(tmp_path, COMPENSATION_ENABLED=True))


def test_a_paid_study_keeps_paying_without_the_setting(tmp_path, monkeypatch):
    create_app(base(tmp_path))  # created with COMPENSATION_ENABLED=true (fixture)
    monkeypatch.delenv("COMPENSATION_ENABLED")
    app = create_app({k: v for k, v in base(tmp_path).items()})
    assert app.config["COMPENSATION_ENABLED"] is True
    assert "pay-callout" in get(app.test_client(), "/?lang=en").data.decode()
    with pytest.raises(RuntimeError, match="created with compensation"):
        create_app(base(tmp_path, COMPENSATION_ENABLED=False))
