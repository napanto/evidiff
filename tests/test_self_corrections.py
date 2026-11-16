# SPDX-License-Identifier: AGPL-3.0-only
"""Participants correct their own submitted pairs on the site (synthetic data only)."""

import json
import re
import secrets
from html.parser import HTMLParser

import pytest
import test_private_export
from itsdangerous import URLSafeTimedSerializer
from test_private_export import read_bundle, run_export
from test_web import Forms, create_app, get, post

from app import corrections, engine
from app import private_export as export
from app.db import connect
from app.instrument import make_path, validate_path

data = test_private_export.data  # the export fixture, reused

ORIGIN = {"base_url": "https://localhost", "headers": {"Origin": "https://localhost"}}


class Prefill(HTMLParser):
    def __init__(self, body):
        super().__init__()
        self.values, self.names = None, set()
        self.feed(body.decode())

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form" and "data-prefill" in attrs:
            self.values = json.loads(attrs["data-prefill"])["values"]
        if tag in ("input", "select", "textarea") and attrs.get("name"):
            self.names.add(attrs["name"])


def start(app, pairs=1, rationale="Original note"):
    """A session that has submitted `pairs` real pairs (practice is off in this app)."""
    client = app.test_client()
    response = post(client, get(client), "/start")
    for _ in range(pairs):
        response = post(
            client, response, "/answer", label="concordant", factor="none", rationale=rationale
        )
    return client, response


def db_of(app):
    return connect(app.config)


def own_answers(app, client):
    page = get(client, "/submitted?lang=en").data.decode()
    return re.findall(r'href="/submitted/([0-9a-f]+)\?', page)


def correction_page(client, assignment, lang="en"):
    return get(client, f"/submitted/{assignment}?lang={lang}")


def correct(client, assignment, path, rationale="Original note"):
    form = Forms(correction_page(client, assignment).data).forms["/correction"]
    form.update(path=json.dumps(path), rationale=rationale)
    return client.post("/correction?lang=en", data=form, **ORIGIN)


def corrections_of(db):
    return [
        (row["id"], row["session_id"], json.loads(row["reason"]))
        for row in db.execute(
            "SELECT * FROM audit WHERE action='participant-correction' ORDER BY id"
        )
    ]


def table(db, name):
    return [dict(row) for row in db.execute(f"SELECT * FROM {name} ORDER BY rowid")]


def test_list_shows_only_this_sessions_real_live_pairs(tmp_path, synthetic):
    app = create_app(
        {
            "SECRET_KEY": secrets.token_hex(32),
            "DATABASE_PATH": str(tmp_path / "app.sqlite3"),
            "BASE_URL": "https://localhost",
            "PRACTICE_ENABLED": True,
        }
    )
    db = db_of(app)

    def practice_then(pairs):
        client = app.test_client()
        response = post(client, get(client), "/start")
        response = post(client, response, "/practice-begin")
        practice = db.execute(
            "SELECT * FROM assignments WHERE kind='practice' ORDER BY created DESC,rowid DESC"
        ).fetchone()
        item = synthetic[practice["item_id"]]
        response = post(client, response, "/answer", label=item["answer"], factor=item["factor"])
        response = post(client, response, "/practice-next")
        for _ in range(pairs):
            response = post(client, response, "/answer", label="concordant", factor="none")
        return client, practice, item

    client, practice, item = practice_then(3)
    practice_then(1)
    sid = practice["session_id"]
    real = db.execute(
        "SELECT a.assignment_id,i.data FROM answers a JOIN items i ON i.id=a.item_id "
        "WHERE a.session_id=? AND a.kind='real' ORDER BY a.submitted,a.id",
        (sid,),
    ).fetchall()
    assert len(real) == 3
    retired = real[1]["assignment_id"]
    db.execute(
        "UPDATE items SET retired=1 WHERE id=(SELECT item_id FROM answers WHERE assignment_id=?)",
        (retired,),
    )
    page = get(client, "/submitted?lang=it").data.decode()
    listed = re.findall(r'href="/submitted/([0-9a-f]+)\?', page)
    assert listed == [real[0]["assignment_id"], real[2]["assignment_id"]]
    assert "Coppia 1" in page and "Coppia 2" in page and "Coppia 3" not in page
    assert page.count("Rivedi e correggi") == 2 and "Consegnata il " in page
    for row, shown in ((real[0], True), (real[1], False), (real[2], True)):
        title = json.loads(row["data"])["a"]["article"]["title"]
        assert (title[:40] in page) == shown
    assert item["a"]["article"]["title"][:40] not in page  # the practice pair
    other_title = json.loads(
        db.execute(
            "SELECT i.data FROM answers a JOIN items i ON i.id=a.item_id WHERE a.session_id!=?",
            (sid,),
        ).fetchone()[0]
    )["a"]["article"]["title"]
    assert other_title[:40] not in page
    # Retired and practice reads cannot be opened either.
    assert correction_page(client, retired).status_code == 404
    assert correction_page(client, practice["id"]).status_code == 404
    # Nothing submitted yet: a short plain message.
    empty = app.test_client()
    post(empty, get(empty), "/start")
    page = get(empty, "/submitted?lang=en").data.decode()
    assert "You have not submitted any real pairs yet" in page and "Review and correct" not in page
    assert get(app.test_client(), "/submitted").status_code == 302
    db.close()


def test_prefill_is_the_latest_version_and_matches_the_form(app):
    client, _ = start(app)
    (assignment,) = own_answers(app, client)
    db = db_of(app)
    answer = db.execute("SELECT * FROM answers").fetchone()
    page = correction_page(client, assignment)
    form = Prefill(page.data)
    assert form.values == corrections.form_values(json.loads(answer["path"]), "Original note")
    assert set(form.values) <= form.names  # every value has its control on the pair screen
    text = page.data.decode()
    assert "You are correcting an answer submitted on " in text
    assert "The original answer stays recorded; your pay does not change." in text
    assert "The choices are the ones you submitted" in text
    assert "Save the correction" in text and "Back to the list without changes" in text
    assert "Correction · Pair 1" in text and 'action="/correction?' in text
    assert "can no longer be changed" not in text and 'name="comment"' not in text
    # The language switch stays on this correction page.
    assert f'href="/submitted/{assignment}?lang=it"' in text
    complex_path = make_path("apparent_contradiction", "other")
    complex_path["q5"]["detail"] = "Different follow-up"
    complex_path["q1"]["a"]["sample_size"] = {
        "answer": "no",
        "problems": ["missing_from_extraction"],
    }
    complex_path["q1"]["b"]["context"] = {"answer": "cannot_tell", "problems": []}
    complex_path["q1_relevance"] = "not_material"
    assert correct(client, assignment, complex_path, "Corrected note").status_code == 303
    form = Prefill(correction_page(client, assignment).data)
    expected = validate_path(complex_path, "Corrected note")["path"]
    assert form.values == corrections.form_values(expected, "Corrected note")
    assert form.values["q5.detail"] == "Different follow-up"
    assert form.values["q1.a.sample_size.problems"] == ["missing_from_extraction"]
    assert set(form.values) <= form.names
    assert "your latest correction, saved on" in correction_page(client, assignment).data.decode()
    db.close()


def test_form_values_cover_every_branch():
    path = make_path("not_comparable")
    path["q2"]["exposure"] = {"answer": "no", "reason": "molecule_class"}
    path["q2"]["comparison"] = {"answer": "no", "reason": "other", "detail": "Other unit"}
    path["q2_primary"] = "comparison"
    values = corrections.form_values(validate_path(path)["path"], "")
    assert values["q2.exposure.reason"] == "molecule_class"
    assert values["q2.comparison.reason"] == "other"
    assert values["q2.comparison.detail"] == "Other unit"
    assert values["q2.primary"] == "comparison" and "q2.outcome.reason" not in values
    # One failed check: the form derives the main reason itself and has nothing to restore.
    single = corrections.form_values(validate_path(make_path("not_comparable"))["path"], "")
    assert "q2.primary" not in single and single["q2.outcome"] == "no"


def test_first_correction_then_a_chained_second(app):
    client, _ = start(app)
    (assignment,) = own_answers(app, client)
    db = db_of(app)
    before = table(db, "answers")
    response = correct(client, assignment, make_path("not_replicated"))
    assert response.status_code == 303
    assert "note=corrected" in response.headers["Location"]
    ((first, sid, record),) = corrections_of(db)
    assert sid == before[0]["session_id"]
    assert record["answer_id"] == before[0]["id"]
    assert record["answers_row_modified"] is False
    assert record["source"] == export.SELF_SERVICE_SOURCE
    assert record["recorded_by"] == export.SELF_SERVICE_RECORDED_BY == "participant"
    instrument = export.sha256(export.instrument_bytes(app.config))
    assert instrument in record["disclosure"]
    assert record["derived_with"] == {
        "instrument_version": "2.0",
        "instrument_export_sha256": instrument,
    }
    assert record["supersedes_audit_id"] is None
    assert record["changes_relative_to"] == "original answer"
    assert set(record["changes"]) == {"q3", "q4"}
    assert record["derived_old"]["label"] == "concordant"
    assert record["derived_new"]["label"] == "not_replicated"
    assert record["corrected_rationale"] == "Original note"
    page = get(client, response.headers["Location"]).data.decode()
    assert "Correction saved: pair 1." in page and "Corrected on " in page
    # A second correction, also of the note, supersedes the first.
    assert correct(client, assignment, make_path("contradictory"), "New note").status_code == 303
    (_, _, first_again), (second, _, chained) = corrections_of(db)
    assert first_again == record
    assert chained["supersedes_audit_id"] == first
    assert chained["changes_relative_to"] == f"corrected_path of audit {first}"
    assert chained["derived_old"] == record["derived_new"]
    assert chained["derived_new"]["label"] == "contradictory"
    assert chained["changes"]["rationale"] == {"old": "Original note", "new": "New note"}
    assert chained["corrected_rationale"] == "New note"
    assert second > first
    # Every record passes the export's own record check; the answers row never changes.
    for audit_id, _, _ in corrections_of(db):
        export.correction_record(
            db.execute("SELECT * FROM audit WHERE id=?", (audit_id,)).fetchone()
        )
    assert table(db, "answers") == before
    db.close()


def test_saving_without_changes_writes_nothing_and_says_so(app):
    client, _ = start(app)
    (assignment,) = own_answers(app, client)
    db = db_of(app)
    original = json.loads(db.execute("SELECT path FROM answers").fetchone()[0])
    before = table(db, "audit")
    # Same path, same note up to the whitespace a normal answer also strips.
    response = correct(client, assignment, original, "  Original note  ")
    assert response.status_code == 303 and "note=unchanged" in response.headers["Location"]
    assert table(db, "audit") == before
    page = get(client, response.headers["Location"]).data.decode()
    assert "No changes from the latest version: nothing was recorded." in page
    assert "Corrected on" not in page
    # After a correction, saving that same version again is also no change.
    assert correct(client, assignment, make_path("not_replicated")).status_code == 303
    response = correct(client, assignment, make_path("not_replicated"))
    assert "note=unchanged" in response.headers["Location"]
    assert len(corrections_of(db)) == 1
    db.close()


def test_invalid_answers_are_refused_as_in_a_normal_submission(app):
    client, _ = start(app)
    (assignment,) = own_answers(app, client)
    incomplete = make_path("concordant")
    del incomplete["q3"]
    assert correct(client, assignment, incomplete).status_code == 400
    assert correct(client, assignment, make_path("concordant"), "x" * 1501).status_code == 400
    db = db_of(app)
    assert corrections_of(db) == []
    db.close()


def test_another_sessions_answer_is_refused(app):
    owner, _ = start(app)
    intruder, _ = start(app)
    (theirs,) = own_answers(app, owner)
    (mine,) = own_answers(app, intruder)
    assert theirs != mine
    assert correction_page(intruder, theirs).status_code == 404
    assert theirs not in get(intruder, "/submitted").data.decode()
    # The owner's form is bound to the owner's session.
    form = Forms(correction_page(owner, theirs).data).forms["/correction"]
    form.update(path=json.dumps(make_path("not_replicated")), rationale="")
    assert intruder.post("/correction", data=form, **ORIGIN).status_code == 403
    # Even a validly signed form naming someone else's pair finds nothing.
    db = db_of(app)
    sid = db.execute("SELECT session_id FROM answers WHERE assignment_id=?", (mine,)).fetchone()[0]
    signer = URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="form-v1")
    form["_form"] = signer.dumps(
        {
            "nonce": secrets.token_hex(16),
            "endpoint": "correction",
            "sid": sid,
            "issued": 0,
            "assignment": theirs,
        }
    )
    assert intruder.post("/correction", data=form, **ORIGIN).status_code == 404
    # Without a session there is nothing to see or send.
    stranger = app.test_client()
    assert get(stranger, "/submitted").status_code == 302
    assert correction_page(stranger, theirs).status_code == 302
    assert corrections_of(db) == []
    db.close()


def test_payments_assignments_meter_and_quality_are_unchanged(app):
    client, _ = start(app, pairs=2)
    db = db_of(app)
    sid = db.execute("SELECT session_id FROM answers").fetchone()[0]

    def state():
        return {
            "tables": {
                name: table(db, name)
                for name in ("answers", "assignments", "sessions", "identities", "items")
            },
            "earnings": engine.earnings(db, app.config, sid),
            "ledger": engine.ledger(db, app.config),
            "progress": engine.study_progress(db, app.config),
            "quality": engine.quality_report(db, app.config, sid),
            "closure": engine.closure(db, app.config),
            "stop": engine.site_stop_reason(db, app.config, sid),
            "votes": {
                item: [dict(r) for r in engine.votes(db, item)]
                for (item,) in db.execute("SELECT item_id FROM answers")
            },
        }

    before = state()
    for assignment in own_answers(app, client):
        assert correct(client, assignment, make_path("contradictory"), "Changed").status_code == 303
    assert len(corrections_of(db)) == 2
    assert state() == before
    db.close()


def test_export_applies_the_last_site_correction(data, app, tmp_path):
    _, db, _ = data
    client, _ = start(app, pairs=2)
    first, second = own_answers(app, client)
    answers_before = table(db, "answers")
    assert correct(client, first, make_path("not_replicated")).status_code == 303
    assert correct(client, first, make_path("contradictory"), "Second thoughts").status_code == 303
    # A note-only correction is a correction too.
    assert correct(client, second, make_path("concordant"), "Only the note").status_code == 303
    result = run_export(data, tmp_path / "bundle")
    assert result.exit_code == 0, result.output
    rows = [
        json.loads(line)
        for line in (tmp_path / "bundle" / "corrections.jsonl").read_text().splitlines()
    ]
    for row in rows:
        export.validate(row, "participant_correction")
    by_read = {}
    for row in rows:
        by_read.setdefault(row["read_id"], []).append(row)
    assert [r["applied"] for r in by_read[first]] == [False, True]
    applied = by_read[first][1]
    assert applied["derived_new"]["label"] == "contradictory"
    assert applied["supersedes_audit_id"] == by_read[first][0]["audit_id"]
    assert applied["corrected_rationale"] == "Second thoughts"
    assert by_read[first][0]["corrected_rationale"] == "Original note"
    assert applied["source"] == export.SELF_SERVICE_SOURCE
    assert applied["recorded_by"] == "participant"
    (note_only,) = by_read[second]
    assert note_only["applied"] and note_only["changes"] == {
        "rationale": {"old": "Original note", "new": "Only the note"}
    }
    assert note_only["derived_new"] == note_only["derived_old"]
    assert note_only["corrected_rationale"] == "Only the note"
    answers, meta = read_bundle(tmp_path / "bundle")
    assert meta["participant_corrections"] == 3
    assert meta["participant_corrections_sha256"] == export.sha256(
        (tmp_path / "bundle" / "corrections.jsonl").read_bytes()
    )
    # The answers export still carries the original answers.
    assert {a["label"] for a in answers} == {"concordant"}
    assert {a["rationale"] for a in answers} == {"Original note"}
    assert table(db, "answers") == answers_before


def test_closed_collection_keeps_the_list_and_refuses_corrections(app):
    client, _ = start(app)
    (assignment,) = own_answers(app, client)
    form = Forms(correction_page(client, assignment).data).forms["/correction"]
    form.update(path=json.dumps(make_path("not_replicated")), rationale="")
    db = db_of(app)
    db.execute("UPDATE metadata SET value='1' WHERE key='manual_closed'")
    page = get(client, "/submitted?lang=en").data.decode()
    assert "Pair 1" in page and "can no longer be corrected" in page
    assert "Review and correct" not in page
    response = correction_page(client, assignment)
    assert response.status_code == 302 and "/submitted" in response.headers["Location"]
    response = client.post("/correction", data=form, **ORIGIN)
    assert response.status_code == 303 and "/submitted" in response.headers["Location"]
    assert corrections_of(db) == []
    db.close()


def test_saves_are_rate_limited_per_session(app, monkeypatch):
    monkeypatch.setattr(corrections, "RATE_LIMIT", 2)
    client, _ = start(app)
    (assignment,) = own_answers(app, client)
    for label in ("not_replicated", "contradictory"):
        assert correct(client, assignment, make_path(label)).status_code == 303
    response = correct(client, assignment, make_path("concordant"), "Third")
    assert response.status_code == 429
    assert "Wait 15 minutes before saving another correction" in response.data.decode()
    db = db_of(app)
    assert len(corrections_of(db)) == 2
    # Another session has its own allowance.
    other, _ = start(app)
    (theirs,) = own_answers(app, other)
    assert correct(other, theirs, make_path("not_replicated")).status_code == 303
    # The window expires like the resume limit.
    db.execute("UPDATE rate_limits SET until=0")
    assert correct(client, assignment, make_path("concordant"), "Third").status_code == 303
    db.close()


def test_works_mid_block_and_after_finishing(app):
    client, _ = start(app, pairs=1)
    db = db_of(app)
    reserved = db.execute("SELECT id FROM assignments WHERE state='reserved'").fetchall()
    assert reserved  # stopped mid-block
    (assignment,) = own_answers(app, client)
    assert correct(client, assignment, make_path("not_replicated")).status_code == 303
    assert db.execute("SELECT id FROM assignments WHERE state='reserved'").fetchall() == reserved
    # The next pair is still the one that was waiting.
    assert b'class="answer-form' in get(client, "/work").data
    finished = post(
        client,
        get(client, "/finish"),
        "/finish",
        first_name="Synthetic",
        last_name="Person",
        eligibility="yes",
        programme="medicine",
        year="3",
        confirm_below="yes",
    )
    assert b"Your contribution matters" in finished.data
    assert get(client, "/submitted").status_code == 200
    assert correct(client, assignment, make_path("contradictory")).status_code == 303
    assert len(corrections_of(db)) == 2
    db.close()


def links(page):
    text = page.data.decode()
    return text.count(">Review the pairs you submitted") + text.count(
        ">Rivedi le coppie consegnate"
    )


def test_links_appear_where_participants_return_but_never_on_the_pair_screen(app):
    client = app.test_client()
    response = post(client, get(client), "/start")
    assert links(get(client, "/")) == 0  # nothing submitted yet
    response = post(client, response, "/answer", label="concordant", factor="none")
    assert b'class="answer-form' in response.data and links(response) == 0
    assert links(get(client, "/work")) == 0
    # The «Resume · Your code» box on other pages offers it once.
    home = get(client, "/?lang=it")
    assert links(home) == 1 and "Rivedi le coppie consegnate" in home.data.decode()
    assert links(get(client, "/rules")) == 1
    # The page that asks whether to continue or finish: once, in the page itself.
    while b'class="answer-form' in response.data:
        response = post(client, response, "/answer", label="concordant", factor="none")
    assert b"/more?" in response.data and links(response) == 1
    assert b'class="submitted-link"' in response.data.split(b"</section>")[0]
    # The final page: once, in the page itself.
    final = post(
        client,
        get(client, "/finish"),
        "/finish",
        first_name="Synthetic",
        last_name="Person",
        eligibility="yes",
        programme="medicine",
        year="3",
    )
    assert b"Your contribution matters" in final.data and links(final) == 1
    assert b'class="submitted-link"' in final.data.split(b"</section>")[0]
    # The list page itself does not link to itself from the recovery box.
    assert links(get(client, "/submitted")) == 0


def test_returning_with_the_code_offers_the_list(app):
    client = app.test_client()
    started = post(client, get(client), "/start")
    code = re.search(rb'data-new-code="([A-Z0-9-]+)"', started.data).group(1).decode()
    response = started
    while b'class="answer-form' in response.data:
        response = post(client, response, "/answer", label="concordant", factor="none")
    other = app.test_client()
    resumed = post(other, get(other), "/resume", code=code)
    assert resumed.status_code == 200 and links(resumed) == 1
    assert get(other, "/submitted").status_code == 200


@pytest.mark.parametrize(
    "stamp,lang,expected",
    [
        ("2026-11-14T15:42:00+01:00", "it", "il 14 novembre 2026 alle 15:42"),
        ("2026-11-14T15:42:00+01:00", "en", "on 14 November 2026 at 15:42"),
        ("2026-12-01T09:05:00+01:00", "it", "il 1° dicembre 2026 alle 9:05"),
        ("2026-11-08T01:30:00+01:00", "it", "l’8 novembre 2026 all’1:30"),
        ("2026-11-11T00:00:00+01:00", "it", "l’11 novembre 2026 alle 0:00"),
        # Stored instants are UTC epochs; the page shows Rome time.
        ("2026-11-14T23:30:00+00:00", "en", "on 15 November 2026 at 0:30"),
    ],
)
def test_dates_are_shown_in_rome_time(stamp, lang, expected):
    assert corrections.when(export.epoch(stamp), lang) == expected
