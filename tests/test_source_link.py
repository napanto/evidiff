"""Every public page links to the program's source code (AGPL-3.0 section 13).

The link points to the public repository and is the same with or without a session,
open or closed. SOURCE_URL is not part of the configuration snapshot, so adding it
leaves the frozen configuration hash of the study unchanged. Synthetic data only.
"""

import pytest

from app import create_app
from app.db import configuration_snapshot

SOURCE = "https://github.com/napanto/evidiff"
PAGES = ("/", "/rules", "/privacy", "/guidelines", "/no-such-page")


def page(client, path, lang):
    return client.get(f"{path}?lang={lang}", base_url="https://localhost").data.decode()


@pytest.mark.parametrize("closed", [False, True])
def test_every_public_page_links_to_the_source(cfg, closed):
    app = create_app(cfg)
    if closed:
        assert app.test_cli_runner().invoke(args=["close", "--reason", "synthetic"]).exit_code == 0
    client = app.test_client()
    for lang, label in (("it", "Codice sorgente"), ("en", "Source code")):
        for path in PAGES:
            html = page(client, path, lang)
            assert f'<a href="{SOURCE}" rel="license noopener">{label}</a> (AGPL-3.0)' in html, (
                lang,
                path,
            )


def test_the_source_url_can_be_changed_or_removed(cfg):
    other = "https://example.org/fork"
    assert other in page(create_app({**cfg, "SOURCE_URL": other}).test_client(), "/", "en")
    assert "Source code" not in page(create_app({**cfg, "SOURCE_URL": ""}).test_client(), "/", "en")


def test_the_source_url_does_not_change_the_configuration_snapshot(cfg):
    assert "SOURCE_URL" not in configuration_snapshot(create_app(cfg).config)
