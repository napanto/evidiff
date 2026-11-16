# SPDX-License-Identifier: AGPL-3.0-only
import itertools
import json
import re
import secrets
from html.parser import HTMLParser
from urllib.parse import urlsplit

import pytest

from app import create_app as app_factory
from app.config import ROOT, settings
from app.db import connect
from app.instrument import make_path


def create_app(overrides):
    return app_factory(
        {"TESTING": True, "PAIR_FILE": str(ROOT / "content/preview_pairs.jsonl"), **overrides}
    )


class Forms(HTMLParser):
    def __init__(self, body):
        super().__init__()
        self.forms = {}
        self.current = None
        self.feed(body.decode() if isinstance(body, bytes) else body)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.current = urlsplit(attrs.get("action", "")).path
            self.forms[self.current] = {}
        if tag == "input" and self.current and attrs.get("name"):
            self.forms[self.current][attrs["name"]] = attrs.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self.current = None


def get(client, path="/"):
    return client.get(path, base_url="https://localhost")


def post(client, response, endpoint, **fields):
    data = Forms(response.data).forms[endpoint]
    if "label" in fields:
        label = fields.pop("label")
        factor = fields.pop("factor", "population")
        data["path"] = json.dumps(make_path(label, factor if factor != "none" else "population"))
    data.update(fields)
    return client.post(
        endpoint + "?lang=en",
        data=data,
        base_url="https://localhost",
        headers={"Origin": "https://localhost"},
        follow_redirects=True,
    )


def snapshot(app):
    db = connect(app.config)
    try:
        return {
            r[0]: db.execute(f'SELECT COUNT(*) FROM "{r[0]}"').fetchone()[0]
            for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    finally:
        db.close()


def test_get_readonly_and_security_headers(app):
    client = app.test_client()
    before = snapshot(app)
    for path in (
        "/",
        "/work",
        "/rules",
        "/privacy",
        "/guidelines",
        "/finish",
        "/healthz",
        "/robots.txt",
    ):
        response = get(client, path)
        assert response.status_code in (200, 302)
        assert "Set-Cookie" not in response.headers
        assert "default-src 'self'" in response.headers["Content-Security-Policy"]
        assert response.headers["Referrer-Policy"] == "same-origin"
        assert "noindex" in response.headers["X-Robots-Tag"]
    assert snapshot(app) == before


@pytest.mark.parametrize(
    "tutorial,qualification,practice,controls,preview,technical",
    list(itertools.product((False, True), repeat=6)),
)
def test_every_flag_combination(
    tmp_path, synthetic, tutorial, qualification, practice, controls, preview, technical
):
    app = create_app(
        {
            "SECRET_KEY": secrets.token_hex(32),
            "DATABASE_PATH": str(tmp_path / "app.sqlite3"),
            "BASE_URL": "https://localhost",
            "TUTORIAL_ENABLED": tutorial,
            "QUALIFICATION_ENABLED": qualification,
            "PRACTICE_ENABLED": practice,
            "HIDDEN_CONTROLS_ENABLED": controls,
            "SHOW_TECHNICAL_DETAILS": technical,
            "PREVIEW_MODE": preview,
            "QUALITY_MIN_MEDIAN_SECONDS": 0,
        }
    )
    client = app.test_client()
    response = post(client, get(client), "/start")
    assert response.status_code == 200
    if tutorial:
        assert b"/tutorial?" in response.data
        response = post(client, response, "/tutorial")
    if qualification:
        for i in range(1, 7):
            item = synthetic[f"q1-{i}"]
            response = post(
                client, response, "/qualification", label=item["answer"], factor=item["factor"]
            )
            assert response.status_code == 200
        assert b"Test passed" in response.data
        response = post(client, response, "/qualification-next")
    if practice:
        assert b"/practice-begin?" in response.data
        response = post(client, response, "/practice-begin")
    assert b'class="answer-form' in response.data
    db = connect(app.config)
    assignments = db.execute("SELECT * FROM assignments ORDER BY position").fetchall()
    assert (assignments[0]["kind"] == "practice") == practice
    # With practice, admission reserves only the practice pair; real pairs follow its answer.
    assert all(a["kind"] == "practice" for a in assignments) == practice
    while a := db.execute(
        "SELECT * FROM assignments WHERE state='reserved' ORDER BY position LIMIT 1"
    ).fetchone():
        item = synthetic.get(a["item_id"])
        label = item["answer"] if item else "concordant"
        factor = item["factor"] if item else "none"
        response = post(client, response, "/answer", label=label, factor=factor)
        assert response.status_code == 200
        if a["kind"] == "practice":
            assert b"An example, step by step" in response.data
            response = post(client, response, "/practice-next")
            assert b'class="answer-form' in response.data
    assignments = db.execute("SELECT * FROM assignments ORDER BY position").fetchall()
    assert any(a["kind"] == "control" for a in assignments) == controls
    assert b"/more?" in response.data
    response = post(
        client,
        get(client, "/finish"),
        "/finish",
        first_name="Test",
        last_name="Person",
        eligibility="yes",
        programme="biotech_ai",
        year="2",
    )
    assert response.status_code == 200 and b"Your contribution matters" in response.data
    assert db.execute("SELECT COUNT(*) FROM identities").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM answers WHERE paid=1").fetchone()[0] >= 5
    db.close()


def test_csrf_size_validation_and_duplicate_start(app):
    client = app.test_client()
    landing = get(client)
    form = Forms(landing.data).forms["/start"]
    assert (
        client.post(
            "/start",
            data=form,
            base_url="https://localhost",
            headers={"Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/start", data={}, base_url="https://localhost", headers={"Origin": "https://localhost"}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/start",
            data={"blob": "x" * 17000},
            base_url="https://localhost",
            headers={"Origin": "https://localhost"},
        ).status_code
        == 413
    )
    first = post(client, landing, "/start")
    assert b"HttpOnly" in first.headers.get("Set-Cookie", "").encode()
    assert "Secure" in first.headers["Set-Cookie"] and "SameSite=Lax" in first.headers["Set-Cookie"]
    second = post(client, landing, "/start")
    assert second.status_code == 200
    assert snapshot(app)["sessions"] == 1
    assert snapshot(app)["assignments"] == 1  # one pair at a time
    assert get(client, "/?name=bad").status_code == 400


def test_cookie_resume_code_resume_and_only_hashes(app):
    client = app.test_client()
    started = post(client, get(client), "/start")
    code = re.search(rb'data-new-code="([A-Z0-9-]+)"', started.data).group(1).decode()
    cookie = client.get_cookie("participant").value
    assert get(client, "/work").status_code == 200
    other = app.test_client()
    resumed = post(other, get(other), "/resume", code=code)
    assert resumed.status_code == 200 and b'class="answer-form' in resumed.data
    assert code not in str(resumed.headers)
    db = connect(app.config)
    person = db.execute("SELECT * FROM sessions").fetchone()
    assert person["code_hash"] != code and person["token_hash"] != cookie
    assert person["code_hint"] == code[-4:]
    assert get(client, "/work").status_code == 302  # Token rotates across devices.
    assert get(other, "/work").status_code == 200
    db.close()


def test_answer_idempotency_optional_rationale_and_crash_restart(app):
    client = app.test_client()
    response = post(client, get(client), "/start")
    data = Forms(response.data).forms["/answer"]
    data.update(path=json.dumps(make_path("concordant")), rationale="")
    kwargs = {
        "data": data,
        "base_url": "https://localhost",
        "headers": {"Origin": "https://localhost"},
    }
    assert client.post("/answer", **kwargs).status_code == 303
    assert client.post("/answer", **kwargs).status_code == 303
    assert snapshot(app)["answers"] == 1
    # Recreate the app and all SQLite connections; no state is in process memory.
    restarted = create_app(dict(app.config))
    new_client = restarted.test_client()
    new_client.set_cookie("participant", client.get_cookie("participant").value)
    assert get(new_client, "/work").status_code == 200
    assert snapshot(restarted)["answers"] == 1
    db = connect(app.config)
    assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert db.execute("PRAGMA synchronous").fetchone()[0] == 2
    db.close()


def test_qualification_one_retry_then_failure(tmp_path, synthetic):
    app = create_app(
        {
            "SECRET_KEY": secrets.token_hex(32),
            "DATABASE_PATH": str(tmp_path / "app.sqlite3"),
            "BASE_URL": "https://localhost",
            "QUALIFICATION_ENABLED": True,
        }
    )
    client = app.test_client()
    response = post(client, get(client), "/start")
    for attempt in (1, 2):
        for i in range(1, 7):
            item = synthetic[f"q{attempt}-{i}"]
            label = "concordant" if item["answer"] != "concordant" else "contradictory"
            response = post(client, response, "/qualification", label=label, factor="none")
        response = post(client, response, "/qualification-next")
    assert b"test was not passed" in response.data
    assert snapshot(app)["assignments"] == 0
    assert snapshot(app)["qualification"] == 12


def test_finish_after_manual_closure_and_cli_exports(app, tmp_path):
    client = app.test_client()
    response = post(client, get(client), "/start")
    post(client, response, "/answer", label="concordant", factor="none", rationale="A comparison")
    runner = app.test_cli_runner()
    assert runner.invoke(args=["close", "--reason", "test closure"]).exit_code == 0
    assert b"Collection closed" in get(client, "/work").data
    response = post(
        client,
        get(client, "/finish"),
        "/finish",
        first_name="Example",
        last_name="Name",
        eligibility="yes",
        programme="other",
        other_programme="Review me",
        year="3",
    )
    assert response.status_code == 200
    out = tmp_path / "exports"
    assert runner.invoke(args=["export-answers", "--output", str(out)]).exit_code == 0
    export = (out / "answers.jsonl").read_text()
    assert "Example Name" not in export and "Review me" not in export
    assert len(export.splitlines()) == 1
    assert (
        runner.invoke(args=["payments", "--output", str(tmp_path / "payments.csv")]).exit_code == 0
    )
    assert "Example,Name" in (tmp_path / "payments.csv").read_text()
    assert runner.invoke(args=["purge-identities", "--yes"]).exit_code != 0
    assert snapshot(app)["identities"] == 1
    assert runner.invoke(args=["status"]).exit_code == 0


def test_budget_and_dynamic_content(tmp_path):
    cfg = {"SECRET_KEY": secrets.token_hex(32), "DATABASE_PATH": str(tmp_path / "app.sqlite3")}
    assert settings(cfg)["WORST_CASE_CENTS"] == 20400
    with pytest.raises(ValueError, match="Worst-case"):
        settings({**cfg, "FIXED_FEE_EUR": "6"})
    with pytest.raises(ValueError, match="whole cents"):
        settings({**cfg, "PRICE_PER_PAIR_EUR": "1.001"})
    app = create_app(
        {
            **cfg,
            "FIXED_FEE_EUR": "4",
            "PRICE_PER_PAIR_EUR": "0.50",
            "BUDGET_CAP_EUR": "205",
            "TUTORIAL_ENABLED": True,
            "QUALIFICATION_ENABLED": True,
        }
    )
    text = get(app.test_client(), "/rules?lang=en").data.decode()
    assert "€0.50" in text and "€4.00" in text
    assert "6-pair entry test" in text and "short guide" in text


def test_synthetic_content_complete(synthetic):
    assert len(synthetic) == 23
    for prefix in ("q1", "q2"):
        labels = {synthetic[f"{prefix}-{i}"]["answer"] for i in range(1, 7)}
        assert len(labels) == 6
    for item in synthetic.values():
        assert item["synthetic"] and item["explanation"]["it"] and item["explanation"]["en"]
        for side in ("a", "b"):
            assert not item[side]["article"].get("pmid")


def test_browser_no_referrer_csrf_fetch_metadata(app):
    client = app.test_client()
    form = Forms(get(client).data).forms["/start"]
    assert (
        client.post(
            "/start",
            data=form,
            base_url="https://localhost",
            headers={"Origin": "null", "Sec-Fetch-Site": "cross-site"},
        ).status_code
        == 403
    )
    response = client.post(
        "/start",
        data=form,
        base_url="https://localhost",
        headers={"Origin": "null", "Sec-Fetch-Site": "same-origin"},
    )
    assert response.status_code == 200


def test_budget_preview_readonly_and_quality_cli(app):
    before = snapshot(app)
    runner = app.test_cli_runner()
    result = runner.invoke(
        args=["budget", "--set", "PRICE_PER_PAIR_EUR=2", "--set", "PRACTICE_ENABLED=true"]
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["worst_case_eur"] == 408 and not report["within_budget"]
    assert report["maximum_paid_sessions_at_minimum"] == 40
    assert report["maximum_paid_sessions"] == 204
    assert snapshot(app) == before
    assert runner.invoke(args=["quality"]).exit_code == 0


def test_admission_tracks_minimum_and_stable_item_timer(tmp_path):
    app = create_app(
        {
            "SECRET_KEY": secrets.token_hex(32),
            "DATABASE_PATH": str(tmp_path / "app.sqlite3"),
            "BASE_URL": "https://localhost",
            "MIN_PAYOUT_PAIRS": 7,
            # Without practice, admission requires free pairs for the whole minimum, but
            # assigns one pair at a time.
            "PRACTICE_ENABLED": False,
        }
    )
    client = app.test_client()
    post(client, get(client), "/start")
    db = connect(app.config)
    assert db.execute("SELECT COUNT(*) FROM assignments").fetchone()[0] == 1
    before = db.execute("SELECT started FROM assignments ORDER BY position").fetchall()
    get(client, "/work")
    get(client, "/work")
    after = db.execute("SELECT started FROM assignments ORDER BY position").fetchall()
    assert [r[0] for r in before] == [r[0] for r in after]
    assert before[0][0] is not None
    db.close()
    pool = create_app(
        {
            "SECRET_KEY": secrets.token_hex(32),
            "DATABASE_PATH": str(tmp_path / "small.sqlite3"),
            "BASE_URL": "https://localhost",
            "MIN_PAYOUT_PAIRS": 25,  # more than the 24 preview pairs
            "PRACTICE_ENABLED": False,
        }
    )
    client = pool.test_client()
    post(client, get(client), "/start")
    assert snapshot(pool)["assignments"] == 0


def test_home_stays_reachable_after_starting_and_pause_page_is_gone(app):
    client = app.test_client()
    started = post(client, get(client), "/start")
    assert started.status_code == 200
    home = get(client, "/?lang=it")
    assert home.status_code == 200
    page = home.data.decode()
    assert "Torna al lavoro" in page and "/work" in page
    assert 'action="/start' not in page and "resume-card" not in page
    assert get(client, "/pause").status_code == 404


def test_home_shows_study_progress_bar_once(app):
    page = get(app.test_client(), "/?lang=it").data.decode()
    assert page.count('class="study-meter"') == 1 and 'class="study-progress"' not in page
    assert '<progress class="study-meter-bar" max="100" value="0"' in page
    assert "più vicino alla fine" not in page
    other = get(app.test_client(), "/rules?lang=it").data.decode()
    assert 'class="study-progress"' in other and "study-meter" not in other


def test_pages_opt_out_of_cdn_email_obfuscation(app):
    # A CDN would otherwise rewrite the contact address and inject
    # a decoder script.
    app.config["CONTACT_EMAIL"] = "contact@example.org"
    page = get(app.test_client(), "/?lang=it").data.decode()
    assert page.count("<!--email_off-->") == 1 and page.count("<!--/email_off-->") == 1
    assert page.index("<!--email_off-->") < page.index("mailto:") < page.index("<!--/email_off-->")


def test_practice_first_reserves_real_pairs_only_after_its_answer(tmp_path, synthetic):
    app = create_app(
        {
            "SECRET_KEY": secrets.token_hex(32),
            "DATABASE_PATH": str(tmp_path / "app.sqlite3"),
            "BASE_URL": "https://localhost",
            "PRACTICE_ENABLED": True,
        }
    )
    client = app.test_client()
    response = post(client, get(client), "/start")
    db = connect(app.config)
    kinds = [r[0] for r in db.execute("SELECT kind FROM assignments ORDER BY position")]
    assert kinds == ["practice"], kinds  # a visitor who only looks holds no real reads
    response = post(client, response, "/practice-begin")
    practice = synthetic[db.execute("SELECT item_id FROM assignments").fetchone()[0]]
    response = post(
        client, response, "/answer", label=practice["answer"], factor=practice["factor"]
    )
    assert db.execute("SELECT COUNT(*) FROM assignments WHERE kind='real'").fetchone()[0] == 0
    response = post(client, response, "/practice-next")
    real = db.execute("SELECT COUNT(*) FROM assignments WHERE kind='real' AND state='reserved'")
    # One real pair at a time; practice plus INITIAL_REAL_BATCH answers still reaches the
    # payment threshold and the checkpoint exactly.
    assert real.fetchone()[0] == 1 and app.config["INITIAL_REAL_BATCH"] == 4
    assert app.config["INITIAL_REAL_BATCH"] + 1 == app.config["MIN_PAYOUT_PAIRS"]
    assert b'class="answer-form' in response.data
    for _ in range(app.config["INITIAL_REAL_BATCH"]):
        assert b"/more?" not in response.data
        response = post(
            client, response, "/answer", label="concordant", factor="none", rationale="A comparison"
        )
    # After practice + 4 the site asks whether to continue or finish, at the threshold.
    assert b"/more?" in response.data
    from app import engine

    sid = db.execute("SELECT id FROM sessions").fetchone()[0]
    earned = engine.earnings(db, app.config, sid)
    assert earned["count"] == app.config["MIN_PAYOUT_PAIRS"] and earned["payable_cents"] > 0
    db.close()


def test_session_with_an_old_block_goes_one_pair_at_a_time_after_practice(tmp_path, synthetic):
    app = create_app(
        {
            "SECRET_KEY": secrets.token_hex(32),
            "DATABASE_PATH": str(tmp_path / "app.sqlite3"),
            "BASE_URL": "https://localhost",
            "PRACTICE_ENABLED": True,
        }
    )
    client = app.test_client()
    response = post(client, get(client), "/start")
    db = connect(app.config)
    sid = db.execute("SELECT id FROM sessions").fetchone()[0]
    # Recreate the old allocation: four real pairs reserved together with the practice.
    items = [r[0] for r in db.execute("SELECT id FROM items ORDER BY id LIMIT 4")]
    for position, item in enumerate(items, start=1):
        db.execute(
            "INSERT INTO assignments(id,session_id,item_id,kind,slot,position,created) "
            "VALUES(?,?,?,'real',1,?,0)",
            (f"old-{position}", sid, item, position),
        )
    response = post(client, response, "/practice-begin")
    practice = synthetic[
        db.execute("SELECT item_id FROM assignments WHERE kind='practice'").fetchone()[0]
    ]
    response = post(
        client, response, "/answer", label=practice["answer"], factor=practice["factor"]
    )
    response = client.post(
        "/practice-next",
        data=Forms(response.data).forms["/practice-next"],
        base_url="https://localhost",
        headers={"Origin": "https://localhost"},
    )
    assert "note=unavailable" not in response.headers["Location"]
    # The old block, never opened, went back to the pool when the practice was answered;
    # the session now holds one pair, given in coverage order.
    reserved = db.execute(
        "SELECT item_id FROM assignments WHERE kind='real' AND state='reserved'"
    ).fetchall()
    assert len(reserved) == 1
    released = db.execute(
        "SELECT COUNT(*) FROM assignments WHERE id LIKE 'old-%' AND state='released'"
    )
    assert released.fetchone()[0] == 4
    db.close()
