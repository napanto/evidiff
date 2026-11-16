# SPDX-License-Identifier: AGPL-3.0-only
import json
import os
import subprocess
import sys

from app.db import connect


def test_abrupt_process_death_committed_and_uncommitted(app):
    config = {"DATABASE_PATH": app.config["DATABASE_PATH"]}
    script = """
import json,os,sys
from app.db import connect,transaction
db=connect(json.loads(sys.stdin.read()))
with transaction(db):
    db.execute("INSERT INTO metadata(key,value) VALUES('crash_committed','yes')")
db.execute('BEGIN IMMEDIATE')
db.execute("INSERT INTO metadata(key,value) VALUES('crash_uncommitted','no')")
os._exit(9)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        input=json.dumps(config),
        text=True,
        env={**os.environ, "PYTHONPATH": "."},
        capture_output=True,
        check=False,
    )
    assert result.returncode == 9
    db = connect(app.config)
    assert (
        db.execute("SELECT value FROM metadata WHERE key='crash_committed'").fetchone()[0] == "yes"
    )
    assert db.execute("SELECT value FROM metadata WHERE key='crash_uncommitted'").fetchone() is None
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    db.close()
