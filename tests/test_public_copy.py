# SPDX-License-Identifier: AGPL-3.0-only
import json

import pytest
from test_web import create_app, get, post

from app.db import configuration_snapshot, connect


@pytest.mark.parametrize("lang", ["it", "en"])
def test_public_copy_and_configured_author_are_presentation_only(app, lang):
    client = app.test_client()
    for path in ("/", "/rules", "/guidelines"):
        text = get(client, path + "?lang=" + lang).data.decode()
        assert "Antonio" not in text
        assert "Sant’Anna" not in text and "Sant'Anna" not in text
        assert "35–45" not in text and "2–4 minutes" not in text
        assert "coverage_summary" not in text and "giudizio finale" not in text
        assert "at least two reads" not in text
    privacy = get(client, "/privacy?lang=" + lang).data.decode()
    assert "[contact address]" in privacy or "[indirizzo di contatto]" in privacy
    assert ("Studio completo allo 0%" if lang == "it" else "Study 0% complete") in get(
        client, "/?lang=" + lang
    ).data.decode()
    assert ("malattie metaboliche" if lang == "it" else "metabolic diseases") in get(
        client, "/?lang=" + lang
    ).data.decode()
    before = configuration_snapshot(app.config)
    changed = create_app(
        {
            **app.config,
            "AUTHOR_BIO_IT": "Autore <script>test</script>",
            "AUTHOR_BIO_EN": "Author <script>test</script>",
        }
    )
    assert configuration_snapshot(changed.config) == before
    assert "AUTHOR_BIO_IT" not in before and "AUTHOR_BIO_EN" not in before
    rules = get(changed.test_client(), "/rules?lang=" + lang).data.decode()
    assert "&lt;script&gt;test&lt;/script&gt;" in rules
    assert "<script>test</script>" not in rules


def test_new_bio_does_not_change_frozen_config_or_version(app):
    db = connect(app.config)
    initial = db.execute("SELECT value FROM metadata WHERE key='config_sha256'").fetchone()[0]
    frozen = json.loads(
        db.execute("SELECT value FROM metadata WHERE key='config_json'").fetchone()[0]
    )
    assert "AUTHOR_BIO_EN" not in frozen
    create_app({**app.config, "AUTHOR_BIO_EN": "A confirmed biography."})
    assert (
        db.execute("SELECT value FROM metadata WHERE key='config_sha256'").fetchone()[0] == initial
    )
    assert (
        db.execute("SELECT value FROM metadata WHERE key='instrument_version'").fetchone()[0]
        == "2.0"
    )
    db.close()


def test_fields_have_one_location_outside_reading_area(app):
    client = app.test_client()
    response = post(client, get(client), "/start")
    body = response.data.decode()
    reading = body.split('<aside class="source-column"', 1)[1].split("</aside>", 1)[0]
    assert 'class="extracted-data"' not in reading
    assert 'class="field-values"' not in reading
    assert 'class="extracted-data"' in body.split('<form class="answer-form', 1)[1]
    assert 'class="comment-disclosure"' not in body  # Production comments remain optional notes.
    assert 'data-instrument="2.0"' in body
