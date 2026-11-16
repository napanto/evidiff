# SPDX-License-Identifier: AGPL-3.0-only
"""Participant notices and language are part of the study's frozen contract."""

import json
from pathlib import Path

import markdown
import pytest

from app.i18n import UI, translate

CONTENT = Path(__file__).resolve().parents[1] / "content"


@pytest.mark.parametrize("lang", ["it", "en"])
def test_privacy_notice_template_is_complete_and_matches_the_copy(lang):
    payload = (CONTENT / f"privacy_{lang}.md").read_text()
    content = json.loads((CONTENT / "copy.json").read_text())
    assert content[lang]["privacy"] == payload
    html = markdown.markdown(payload, extensions=["tables"])
    assert html.count("<table>") == 2
    assert all(f"<strong>{n}." in html for n in range(1, 11))
    assert "participant" in html and "me-draft-" in html
    assert "@" not in payload


def test_supplied_eligibility_declaration_is_verbatim():
    assert UI["it"]["eligibility_declaration"] == (
        "Dichiaro di essere maggiorenne e iscritto/a all'Università di Pisa "
        "a uno dei corsi indicati, oppure laureato/a in uno di essi nello stesso ateneo"
    )
    assert UI["en"]["eligibility_declaration"] == (
        "I declare that I am an adult enrolled at the University of Pisa in one of the "
        "listed programmes, or a graduate of one of them from the same university"
    )


@pytest.mark.parametrize(
    "lang,key,count,expected",
    [
        ("it", "paid_tasks", 1, "1 coppia retribuita completata"),
        ("it", "paid_tasks", 2, "2 coppie retribuite completate"),
        ("it", "real_pairs", 1, "1 coppia reale completata"),
        ("it", "real_pairs", 0, "0 coppie reali completate"),
        ("en", "paid_tasks", 1, "1 paid pair completed"),
        ("en", "paid_tasks", 2, "2 paid pairs completed"),
        ("en", "real_pairs", 1, "1 real pair completed"),
        ("en", "real_pairs", 0, "0 real pairs completed"),
        ("it", "preview_tasks", 1, "1 coppia di prova completata"),
        ("en", "preview_tasks", 1, "1 preview pair completed"),
    ],
)
def test_counted_ui_uses_singular_and_plural(lang, key, count, expected):
    assert translate(lang, key, count=count) == expected


def test_configurable_payment_threshold_uses_singular():
    assert translate("en", "payable_from", minimum=1) == "Payable from 1 pair upwards"
    assert translate("en", "payable_from", minimum=5) == "Payable from 5 pairs upwards"
    assert "1 coppia retribuita su 5" in translate("it", "finish_below_warning", count=1, minimum=5)


def test_configurable_qualification_threshold_uses_singular():
    assert "Serve 1 risposta corretta" in translate("it", "qualification_intro", pass_count=1)
    assert "Servono 4 risposte corrette" in translate("it", "qualification_intro", pass_count=4)
    assert "1 correct answer to continue" in translate("en", "qualification_intro", pass_count=1)
    assert "4 correct answers to continue" in translate("en", "qualification_intro", pass_count=4)


@pytest.mark.parametrize("lang", ["it", "en"])
def test_guidance_has_no_stale_time_or_shortcuts(lang):
    text = (CONTENT / f"guidelines_{lang}.md").read_text()
    copy = json.loads((CONTENT / "copy.json").read_text())[lang]
    all_copy = text + json.dumps(copy, ensure_ascii=False) + str(UI[lang])
    for obsolete in ("2–4", "same comparable fact", "1–6"):
        assert obsolete not in all_copy
    assert "35–45" not in all_copy
    assert "Sant’Anna" not in all_copy and "Sant'Anna" not in all_copy
    assert "## 5." in text


def test_italian_payment_threshold_uses_singular_pair():
    assert translate("it", "payable_from", minimum=1) == "Pagamento da 1 coppia in su"
    assert translate("it", "payable_from", minimum=5) == "Pagamento da 5 coppie in su"
