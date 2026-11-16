# SPDX-License-Identifier: AGPL-3.0-only
import json
import secrets
import time

import pytest

from app import create_app
from app.config import ROOT, settings
from app.db import connect, initialize
from app.engine import uid

# pytest writes its temporary files to .local/pytest (pyproject.toml); .local/ is not
# tracked, so a fresh clone needs the parent directory before the first test.
(ROOT / ".local").mkdir(exist_ok=True)


@pytest.fixture(autouse=True)
def compensation(request, monkeypatch):
    """The study tests describe the paid instance; mark a test `unpaid` to switch it off.

    COMPENSATION_ENABLED is off by default for a new instance, so the paid behaviour is
    set explicitly here, as an operator would for a paid study.
    """
    paid = request.node.get_closest_marker("unpaid") is None
    monkeypatch.setenv("COMPENSATION_ENABLED", "true" if paid else "false")
    if paid:
        # Example terms for the paid tests; a real study sets its own.
        monkeypatch.setenv("PRICE_PER_PAIR_EUR", "1.00")
        monkeypatch.setenv("BUDGET_CAP_EUR", "310")
        monkeypatch.setenv("TARGET_HOURLY_EUR", "10.00")
    return paid


@pytest.fixture
def cfg(tmp_path, compensation):
    return settings(
        {
            "SECRET_KEY": secrets.token_hex(32),
            "DATABASE_PATH": str(tmp_path / "study.sqlite3"),
            "BASE_URL": "https://localhost",
            "TESTING": True,
            "PAIR_FILE": str(ROOT / "content/preview_pairs.jsonl"),
            "PRACTICE_ENABLED": False,
            "HIDDEN_CONTROLS_ENABLED": False,
            "QUALITY_MIN_SHARED_PAIRS": 1000,
            "QUALITY_MIN_SPEED_PAIRS": 1000,
        }
    )


@pytest.fixture
def db(cfg):
    initialize(cfg)
    db = connect(cfg)
    yield db
    db.close()


@pytest.fixture
def synthetic():
    return {i["id"]: i for i in json.loads((ROOT / "content/synthetic_items.json").read_text())}


@pytest.fixture
def app(cfg):
    return create_app(cfg)


def session(db, now=None):
    sid = uid()
    now = time.time() if now is None else now
    db.execute(
        "INSERT INTO sessions(id,token_hash,code_hash,code_hint,created,last_submission,stage) VALUES(?,?,?,?,?,?,?)",
        (sid, uid(), uid(), "TEST", now, now, "work"),
    )
    return sid
