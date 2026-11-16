# SPDX-License-Identifier: AGPL-3.0-only
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS items(id TEXT PRIMARY KEY, data TEXT NOT NULL, fourth_granted INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS sessions(
 id TEXT PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, code_hash TEXT NOT NULL UNIQUE,
 code_hint TEXT NOT NULL, created REAL NOT NULL, last_submission REAL NOT NULL,
 stage TEXT NOT NULL DEFAULT 'ready', attempt INTEGER NOT NULL DEFAULT 1,
 excluded INTEGER NOT NULL DEFAULT 0, quality_failed INTEGER NOT NULL DEFAULT 0,
 fixed_fee INTEGER NOT NULL DEFAULT 0, finished INTEGER NOT NULL DEFAULT 0, manual_quality_override INTEGER NOT NULL DEFAULT 0,
 payment_exception TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS identities(
 session_id TEXT PRIMARY KEY REFERENCES sessions(id), first_name TEXT NOT NULL, last_name TEXT NOT NULL,
 programme TEXT NOT NULL, year TEXT NOT NULL, needs_review INTEGER NOT NULL,
 eligibility_declared INTEGER NOT NULL, other_programme TEXT NOT NULL DEFAULT '', updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS assignments(
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
 item_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('real','control','practice')),
 slot INTEGER, position INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'reserved',
 created REAL NOT NULL, started REAL, replacement INTEGER NOT NULL DEFAULT 0,
 UNIQUE(session_id,item_id));
CREATE UNIQUE INDEX IF NOT EXISTS active_slot ON assignments(item_id,slot)
 WHERE state='reserved' AND kind='real';
CREATE TABLE IF NOT EXISTS answers(
 id INTEGER PRIMARY KEY, assignment_id TEXT NOT NULL UNIQUE REFERENCES assignments(id),
 session_id TEXT NOT NULL REFERENCES sessions(id), item_id TEXT NOT NULL,
 kind TEXT NOT NULL, slot INTEGER, label TEXT NOT NULL, factor TEXT NOT NULL,
 rationale TEXT NOT NULL, seconds REAL NOT NULL, submitted REAL NOT NULL,
 paid INTEGER NOT NULL, replacement INTEGER NOT NULL DEFAULT 0, surplus INTEGER NOT NULL DEFAULT 0,
 late_paid INTEGER NOT NULL DEFAULT 0,
 instrument_version TEXT NOT NULL, pipeline_version TEXT NOT NULL,
 path TEXT NOT NULL, field_problems TEXT NOT NULL, relevance TEXT, other_detail TEXT NOT NULL,
 binary_inconsistent INTEGER NOT NULL, package_sha256 TEXT NOT NULL, config_sha256 TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS qualification(
 session_id TEXT NOT NULL REFERENCES sessions(id), attempt INTEGER NOT NULL,
 item_id TEXT NOT NULL, label TEXT NOT NULL, correct INTEGER NOT NULL,
 submitted REAL NOT NULL, path TEXT NOT NULL, PRIMARY KEY(session_id,attempt,item_id));
CREATE TABLE IF NOT EXISTS actions(id TEXT PRIMARY KEY, session_id TEXT, endpoint TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, session_id TEXT, action TEXT NOT NULL, reason TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS rate_limits(bucket TEXT PRIMARY KEY, count INTEGER NOT NULL, until REAL NOT NULL);
CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY, session_id TEXT, screen TEXT NOT NULL, item_id TEXT, message TEXT NOT NULL, created REAL NOT NULL, answer_id INTEGER UNIQUE REFERENCES answers(id));
CREATE INDEX IF NOT EXISTS answer_item ON answers(item_id,submitted);
CREATE INDEX IF NOT EXISTS session_assignments ON assignments(session_id,position);
"""


def connect(cfg):
    db = sqlite3.connect(cfg["DATABASE_PATH"], timeout=5, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("PRAGMA secure_delete=ON")
    db.execute("PRAGMA busy_timeout=5000")
    return db


def initialize(cfg):
    from .package import load_pairs

    items, package = load_pairs(
        cfg["PAIR_FILE"], preview=cfg["PREVIEW_MODE"], testing=cfg["TESTING"]
    )
    snapshot = configuration_snapshot(cfg)
    config_json = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    config_hash = hashlib.sha256(config_json.encode()).hexdigest()

    path = Path(cfg["DATABASE_PATH"])
    path.parent.mkdir(parents=True, exist_ok=True)
    db = connect(cfg)
    try:
        if db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='metadata'"
        ).fetchone():
            version = db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
            if version and version[0] != "2":
                raise RuntimeError(
                    "This version needs a fresh database; archive the old database first"
                )
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(SCHEMA)
        db.execute("BEGIN IMMEDIATE")
        if "late_paid" not in {r[1] for r in db.execute("PRAGMA table_info(answers)")}:
            db.execute("ALTER TABLE answers ADD COLUMN late_paid INTEGER NOT NULL DEFAULT 0")
        if "retired" not in {r[1] for r in db.execute("PRAGMA table_info(items)")}:
            db.execute("ALTER TABLE items ADD COLUMN retired INTEGER NOT NULL DEFAULT 0")
        preview = int(cfg["PREVIEW_MODE"])
        mode = db.execute("SELECT value FROM metadata WHERE key='preview_mode'").fetchone()
        existing_sessions = db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        if (mode and int(mode[0]) != preview) or (not mode and existing_sessions and preview):
            raise RuntimeError(
                "Preview/production mode differs from this database; archive it and use a fresh database"
            )
        for table in (
            "metadata",
            "items",
            "sessions",
            "identities",
            "assignments",
            "answers",
            "qualification",
            "actions",
            "audit",
            "rate_limits",
            "feedback",
        ):
            if "preview" not in {r[1] for r in db.execute(f"PRAGMA table_info({table})")}:
                db.execute(
                    f"ALTER TABLE {table} ADD COLUMN preview INTEGER NOT NULL DEFAULT {preview}"
                )
        fingerprint = package["package_sha256"]
        db.execute(
            "INSERT OR IGNORE INTO metadata(key,value) VALUES('preview_mode',?)",
            (str(preview),),
        )
        old = db.execute("SELECT value FROM metadata WHERE key='pair_sha256'").fetchone()
        if old and old["value"] != fingerprint:
            raise RuntimeError("Frozen pair data changed; refusing to alter an existing study")
        for item in items:
            db.execute(
                "INSERT OR IGNORE INTO items(id,data) VALUES(?,?)",
                (item["item_id"], json.dumps(item, ensure_ascii=False)),
            )
        db.execute(
            "INSERT OR IGNORE INTO metadata(key,value) VALUES('pair_sha256',?)", (fingerprint,)
        )
        db.execute("INSERT OR IGNORE INTO metadata(key,value) VALUES('manual_closed','0')")
        for key, value in {
            "schema_version": "2",
            "instrument_version": cfg["INSTRUMENT_VERSION"],
            "pipeline_version": package["pipeline_version"],
            "package_source_type": package["source_type"],
            "file_sha256": package["file_sha256"],
            "package_manifest": json.dumps(package, sort_keys=True, separators=(",", ":")),
            "config_sha256": config_hash,
            "config_json": config_json,
        }.items():
            previous = db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
            if previous and previous[0] != value:
                raise RuntimeError(f"Frozen {key} changed; archive this database and start fresh")
            db.execute("INSERT OR IGNORE INTO metadata(key,value) VALUES(?,?)", (key, value))
        purge_ip_fingerprints(db)
        db.commit()
    finally:
        db.close()


# Settings that only matter when compensation is enabled. An instance without
# compensation leaves them out of its frozen snapshot, so it records no amounts.
PAYMENT_SNAPSHOT_KEYS = frozenset(
    {
        "FIXED_FEE_EUR",
        "FIXED_FEE_MIN_PAIRS",
        "PRICE_PER_PAIR_EUR",
        "BUDGET_CAP_EUR",
        "TARGET_HOURLY_EUR",
        "LATE_PAYMENT_SECONDS",
        "FIXED_FEE_CENTS",
        "PRICE_PER_PAIR_CENTS",
        "BUDGET_CAP_CENTS",
        "TARGET_HOURLY_CENTS",
        "MAX_FIXED_FEES",
        "WORST_CASE_CENTS",
    }
)


def configuration_snapshot(cfg):
    """Freeze scientific and financial settings without host paths or secrets.

    With compensation enabled the snapshot has exactly the keys it had before the
    switch existed (COMPENSATION_ENABLED is left out), so existing paid studies keep
    their frozen hash. Without compensation it records COMPENSATION_ENABLED=false and
    no payment settings.
    """
    from .config import settings

    keys = settings({"SECRET_KEY": "snapshot-only"}, validate_budget=False)
    excluded = {
        "SECRET_KEY",
        "DATABASE_PATH",
        "BASE_URL",
        "PAIR_FILE",
        "TESTING",
        "COOKIE_SECURE",
        "MAX_CONTENT_LENGTH",
        "AUTHOR_BIO_IT",
        "AUTHOR_BIO_EN",
        "SHOW_TECHNICAL_DETAILS",
        "CONTACT_EMAIL",
        "SOURCE_URL",
    }
    if cfg.get("COMPENSATION_ENABLED", True):
        excluded.add("COMPENSATION_ENABLED")
    else:
        excluded |= PAYMENT_SNAPSHOT_KEYS
    return {key: cfg[key] for key in keys if key not in excluded}


def stored_compensation(database_path):
    """Compensation as frozen in an existing study database.

    None when there is no database or snapshot yet; True when the snapshot has no
    COMPENSATION_ENABLED key (a paid study, including every study created before the
    switch existed); otherwise the recorded value.
    """
    path = Path(database_path)
    if not path.exists():
        return None
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    try:
        if not db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='metadata'"
        ).fetchone():
            return None
        row = db.execute("SELECT value FROM metadata WHERE key='config_json'").fetchone()
    finally:
        db.close()
    if not row:
        return None
    return bool(json.loads(row[0]).get("COMPENSATION_ENABLED", True))


def purge_ip_fingerprints(db, now=None):
    import time

    return db.execute(
        "DELETE FROM rate_limits WHERE until<=?", (time.time() if now is None else now,)
    ).rowcount


@contextmanager
def transaction(db):
    db.execute("BEGIN IMMEDIATE")
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
