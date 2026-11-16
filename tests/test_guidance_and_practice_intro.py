# SPDX-License-Identifier: AGPL-3.0-only
import pytest
from test_web import Forms, create_app, get, post, snapshot

from app.db import connect
from app.instrument import FIELDS, instrument_copy, make_path, validate_path


@pytest.mark.parametrize("lang", ["it", "en"])
def test_every_check_is_a_question_with_short_howto_and_example(lang):
    copy = instrument_copy(lang)
    for field in FIELDS:
        check = copy["checks"][field]
        assert check["question"].endswith("?") and "{side}" in check["question"]
        assert check["name"] and check["how"] and check["help"] and check["example"]
    for key in ("q1_relevance", "q3", "q4", "q5"):
        assert copy[key + "_title"].endswith("?") and copy["how"][key] and copy["examples"][key]
    for field, question in copy["q2_rows"]:
        assert question.endswith("?") and copy["how"]["q2_" + field]
    assert "p-value" in copy["checks"]["significance"]["how"]
    assert validate_path(make_path("contradictory"))["instrument_version"] == "2.0"


def test_practice_intro_get_readonly_begin_idempotent_and_no_pay(cfg):
    app = create_app({**cfg, "PRACTICE_ENABLED": True})
    client = app.test_client()
    intro = post(client, get(client), "/start")
    assert b"practice-intro" in intro.data and b'class="answer-form' not in intro.data
    before = snapshot(app)
    assert get(client, "/work").status_code == 200 and snapshot(app) == before
    form = Forms(intro.data).forms["/practice-begin"]
    for _ in range(2):
        response = client.post(
            "/practice-begin?lang=en",
            data=form,
            base_url="https://localhost",
            headers={"Origin": "https://localhost"},
            follow_redirects=True,
        )
        assert b"Practice pair" in response.data and b'class="answer-form' in response.data
    db = connect(app.config)
    assert (
        db.execute("SELECT COUNT(*) FROM actions WHERE endpoint='practice_begin'").fetchone()[0]
        == 1
    )
    assert db.execute("SELECT COUNT(*) FROM answers").fetchone()[0] == 0
    # Only the practice pair is reserved until its answer.
    assert db.execute("SELECT COUNT(*) FROM assignments").fetchone()[0] == 1
    assert b"Synthetic example" not in get(client, "/work?lang=it").data
    db.close()


def test_no_intro_if_practice_off(app):
    client = app.test_client()
    response = post(client, get(client), "/start")
    assert b'class="answer-form' in response.data and b"/practice-begin?" not in response.data


def test_practice_ack_is_session_bound(cfg):
    app = create_app({**cfg, "PRACTICE_ENABLED": True})
    first = app.test_client()
    intro = post(first, get(first), "/start")
    second = app.test_client()
    post(second, get(second), "/start")
    response = second.post(
        "/practice-begin",
        data=Forms(intro.data).forms["/practice-begin"],
        base_url="https://localhost",
        headers={"Origin": "https://localhost"},
    )
    assert response.status_code == 403
