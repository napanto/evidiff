# SPDX-License-Identifier: AGPL-3.0-only
"""Quoted on-screen labels and the options the interface offers.

Every instruction names its steps with the exact on-screen labels, quoted; the general
rule comes before the first row check. Q2 and the relevance question offer fewer
options, in the interface only: the server keeps accepting every earlier answer, so a
page loaded before the change can still be submitted, paid and exported.
"""

import html
import json
import re

import pytest
from test_private_export import NOON, data, read_bundle, run_export  # noqa: F401
from test_web import Forms, create_app, get, post

from app import i18n
from app.config import ROOT
from app.db import connect
from app.instrument import DISPLAY_ORDER, FACTORS, FIELDS, instrument_copy, make_path, validate_path
from app.presentation import CODES, FIELD_LABELS, TEXT, claim_sentence, claim_view

SYNTHETIC = {i["id"]: i for i in json.loads((ROOT / "content/synthetic_items.json").read_text())}
QUOTES = {"it": ("«", "»"), "en": ("“", "”")}
# Quotations that are not interface labels: words from abstracts or from the authors,
# values typed by participants, and names of documents.
NOT_LABELS = {
    "it": {
        "significativo",
        "non significativo",
        "p < 0,05 è stato considerato significativo",
        "may",
        "suggests",
        "could",
        "not significant",
        "no better",
        "did not",
        "no difference",
        "nessun effetto",
        "nessun cambiamento",
        "laureata",
        "laureato",
        "potrebbe",
        "suggerisce",
        "Clinical Trial",
        "più basso con lo psyllium che con il placebo",
        "redditi diversi",
        "Regole e compenso",
    },
    "en": {
        "significant",
        "not significant",
        "p < 0.05 was considered significant",
        "may",
        "suggests",
        "could",
        "no better",
        "did not",
        "no difference",
        "no effect",
        "no change",
        "graduate",
        "Clinical Trial",
        "lower with psyllium than with placebo",
        "Rules and pay",
    },
}


def js_labels(lang):
    """Navigation labels the script writes on the buttons."""
    source = (ROOT / "app/static/app.js").read_text()
    found = re.findall(r"it \? '([^']+)' : '([^']+)'", source)
    return {pair[0 if lang == "it" else 1].removesuffix(" →") for pair in found}


def labels(lang):
    """Every label, title and value a participant can see on the task screens."""
    ui = instrument_copy(lang)
    found = set(js_labels(lang))
    for key in ("problems", "relevance_options", "exposure_reasons", "comparison_reasons"):
        found |= {text for _, text in ui[key]}
    for key in ("q4_options", "factors", "q2_rows"):
        found |= {text for _, text in ui[key]}
    for key in (
        "yes",
        "no",
        "cannot_tell",
        "next",
        "back",
        "save",
        "problem_title",
        "q1_relevance_title",
        "reason",
        "primary_reason",
        "q3_title",
        "q4_title",
        "q5_title",
        "q5_factor",
        "note",
    ):
        found.add(ui[key])
        found.add(ui[key].split("? ", 1)[0] + "?" if "? " in ui[key] else ui[key])
    found |= set(ui["keywords"].values()) | set(FIELD_LABELS[lang].values())
    found |= set(TEXT[lang].values()) | set(CODES[lang].values())
    found |= {value for value in i18n.UI[lang].values() if len(value) < 60}
    return found


def instructions(lang):
    """Every participant-facing sentence that can tell what to press."""
    ui = instrument_copy(lang)
    skip = {
        "rows",
        "problems",
        "relevance_options",
        "exposure_reasons",
        "comparison_reasons",
        "q4_options",
        "factors",
        "q2_rows",
        "field_labels",
        "keywords",
    }
    texts = []
    for key, value in ui.items():
        if key in skip:
            continue
        if isinstance(value, str):
            texts.append(value)
        elif key == "checks":
            texts += [text for check in value.values() for text in check.values()]
        elif isinstance(value, dict):
            texts += list(value.values())
    texts.append((ROOT / f"content/guidelines_{lang}.md").read_text())
    copy = json.loads((ROOT / "content/copy.json").read_text())[lang]
    texts += copy["tutorial"] + copy["rules"] + copy["rules_nopay"]
    texts += [SYNTHETIC[f"practice-{n}"]["explanation"][lang] for n in (1, 2, 3)]
    texts += [value for value in i18n.UI[lang].values()]
    return texts


@pytest.mark.parametrize("lang", ["it", "en"])
def test_every_quoted_label_is_shown_on_screen(lang):
    known = labels(lang) | NOT_LABELS[lang]
    left, right = QUOTES[lang]
    unknown = {
        quoted
        for text in instructions(lang)
        for quoted in re.findall(f"{left}([^{right}]+){right}", text)
        if quoted not in known
    }
    assert not unknown, unknown


@pytest.mark.parametrize("lang", ["it", "en"])
def test_no_button_is_named_without_quotes(lang):
    if lang == "it":
        verbs = r"\b(?:[Ss]cegli|[Rr]ispondi|[Pp]remi|[Ss]eleziona|[Ss]egna)\s+(?:prima\s+|poi\s+|solo\s+|anche\s+)?"
        bare = verbs + r"(?:Sì|No|Non posso stabilirlo|Non si può stabilire|Continua|Indietro)\b"
        values = r"(?<!«)\b(?:Non posso stabilirlo|Non estratto|Non riportato)\b(?!»)"
    else:
        verbs = (
            r"\b(?:[Cc]hoose|[Aa]nswer|[Pp]ress|[Ss]elect|[Mm]ark)\s+(?:first\s+|then\s+|only\s+)?"
        )
        bare = verbs + r"(?:Yes|No|Cannot tell|Continue|Back)\b"
        values = r"(?<!“)\b(?:Cannot tell|Not extracted|Not reported)\b(?!”)"
    shown = labels(lang)
    for text in instructions(lang):
        if text in shown:
            continue  # the labels themselves
        assert not re.search(bare, text), text
        assert not re.search(values, text), text


@pytest.mark.parametrize("lang", ["it", "en"])
def test_key_rule_boxes_are_short_and_complete(lang):
    ui = instrument_copy(lang)
    left, right = QUOTES[lang]
    problem = ui["problem_title"].split("? ", 1)[0] + "?"
    for key, text in ui["key_rules"].items():
        sentences = re.split(r"(?<=[.»”])\s+(?=[A-ZÀÈÉÌÒÙ«“])", text)
        assert len(sentences) <= 3, (key, sentences)
        # A No on a row check always leads on to the problem question that opens below it.
        if key.startswith("q1_") and key != "q1_relevance" and f"{left}{ui['no']}{right}" in text:
            assert f"{left}{problem}{right}" in text, key
            assert ("compare sotto" if lang == "it" else "appears below") in text, key


@pytest.mark.parametrize("lang", ["it", "en"])
def test_general_rule_comes_first(lang, cfg):
    ui = instrument_copy(lang)
    left, right = QUOTES[lang]
    for value in (
        ui["no"],
        ui["yes"],
        i18n.UI[lang]["not_extracted"],
        i18n.UI[lang]["not_reported"],
    ):
        assert f"{left}{value}{right}" in ui["q1_frame"]
    guidelines = (ROOT / f"content/guidelines_{lang}.md").read_text()
    assert guidelines.index("Regola generale" if lang == "it" else "General rule") < 1200
    app = create_app({**cfg, "PRACTICE_ENABLED": True})
    client = app.test_client()
    post(client, get(client), "/start")
    intro = client.get(f"/work?lang={lang}", base_url="https://localhost").data.decode()
    assert html.escape(i18n.UI[lang]["practice_intro_rule"], False) in intro
    page = practice_page(client, intro, lang)
    first = page.split('data-step="q1.a.result"', 1)[1].split("</section>", 1)[0]
    assert html.escape(ui["q1_frame"], False) in first
    # The same short line under every row check.
    for side in ("a", "b"):
        for field in FIELDS:
            step = page.split(f'data-step="q1.{side}.{field}"', 1)[1].split("</section>", 1)[0]
            assert html.escape(ui["missing_line"], False) in step


def practice_page(client, intro, lang):
    return client.post(
        f"/practice-begin?lang={lang}",
        data=Forms(intro).forms["/practice-begin"],
        base_url="https://localhost",
        headers={"Origin": "https://localhost"},
        follow_redirects=True,
    ).data.decode()


STEPS = [f"q1.{s}.{f}" for s in "ab" for f in DISPLAY_ORDER] + [
    "q1.relevance",
    "q2.exposure",
    "q2.outcome",
    "q2.comparison",
    "q2.primary",
    "q3",
    "q4",
    "q5.answer",
    "review",
]
NAMES = (
    {"_form", "path", "rationale"}
    | {f"q1.{s}.{f}" for s in "ab" for f in FIELDS}
    | {f"q1.{s}.{f}.problems" for s in "ab" for f in FIELDS}
    | {"q1.relevance", "q2.exposure", "q2.outcome", "q2.comparison", "q2.primary", "q3", "q4"}
    | {"q2.exposure.reason", "q2.comparison.reason", "q2.comparison.detail"}
    | {"q5.answer", "q5.factor", "q5.detail"}
)


@pytest.mark.parametrize("lang", ["it", "en"])
def test_steps_names_and_codes_are_unchanged_and_q2_offers_three_reasons(app, lang):
    client = app.test_client()
    post(client, get(client), "/start")
    page = client.get(f"/work?lang={lang}", base_url="https://localhost").data.decode()
    form = page.split('<form class="answer-form', 1)[1].split("</form>", 1)[0]
    assert re.findall(r'class="task-step[^"]*" data-step="([^"]+)"', form) == STEPS
    assert set(re.findall(r'name="([^"]+)"', form)) == NAMES
    values = {
        name: re.findall(rf'name="{re.escape(name)}" value="([^"]+)"', form)
        for name in ("q1.relevance", "q4", "q3", "q5.answer")
    }
    assert values["q1.relevance"] == ["material", "not_material", "cannot_establish_comparison"]
    assert values["q4"] == ["effect_vs_no_effect", "opposite", "size_only", "insufficient"]
    select = form.split('<select name="q2.comparison.reason"', 1)[1].split("</select>", 1)[0]
    assert re.findall(r'value="([^"]*)"', select) == [
        "",
        "comparator",
        "other",
        "outcome_definition",
    ]
    factor = form.split('<select name="q5.factor"', 1)[1].split("</select>", 1)[0]
    assert re.findall(r'value="([^"]*)"', factor) == ["", *FACTORS]


def old_option_paths():
    """Answers the interface offered before the change and no longer offers."""
    relevance = make_path("concordant")
    relevance = {"q1": relevance["q1"], "q1_relevance": "cannot_establish_comparison"}
    relevance["q1"]["a"]["sample_size"] = {"answer": "cannot_tell", "problems": []}
    reasons = make_path("not_comparable")
    reasons["q2"]["outcome"] = {"answer": "yes"}
    reasons["q2"]["comparison"] = {"answer": "no", "reason": "design"}
    reasons["q2_primary"] = "comparison"
    other = make_path("not_comparable")
    other["q2"]["outcome"] = {"answer": "yes"}
    other["q2"]["comparison"] = {
        "answer": "no",
        "reason": "other",
        "detail": "Different population",
    }
    other["q2_primary"] = "comparison"
    return [relevance, reasons, other]


def test_old_options_remain_valid_on_the_server():
    expected = [
        ("not_comparable", "unknown", ""),
        ("not_comparable", "design", ""),
        ("not_comparable", "other", "Different population"),
    ]
    for path, (label, factor, detail) in zip(old_option_paths(), expected, strict=True):
        result = validate_path(path)
        assert (result["label"], result["factor"], result["other_detail"]) == (
            label,
            factor,
            detail,
        )


def test_a_page_loaded_before_the_change_is_saved_paid_and_exported(
    data,  # noqa: F811 - the export fixture
    app,
    tmp_path,
    monkeypatch,
):
    import time

    _, db, _ = data
    monkeypatch.setattr(time, "time", lambda: NOON - 300)
    for path in old_option_paths():
        client = app.test_client()
        page = post(client, get(client), "/start")
        response = post(client, page, "/answer", path=json.dumps(path), rationale="")
        assert response.status_code == 200
    rows = db.execute("SELECT path,label,factor,paid FROM answers ORDER BY submitted").fetchall()
    assert len(rows) == 3 and all(row["paid"] == 1 for row in rows)
    assert sorted(row["factor"] for row in rows) == ["design", "other", "unknown"]
    monkeypatch.setattr(time, "time", lambda: NOON)
    output = tmp_path / "bundle"
    result = run_export(data, output)
    assert result.exit_code == 0, result.output
    exported, _ = read_bundle(output)
    assert sorted(row["factor"] for row in exported) == ["design", "other", "unknown"]
    assert {row["relevance"] for row in exported} == {"cannot_establish_comparison", "not_needed"}


@pytest.mark.parametrize("lang", ["it", "en"])
def test_static_files_and_pages_are_never_reused_from_a_cache(app, lang):
    client = app.test_client()
    for path in (
        "/static/app.js",
        "/static/style.css",
        f"/?lang={lang}",
        f"/guidelines?lang={lang}",
    ):
        response = client.get(path, base_url="https://localhost")
        assert response.status_code == 200, path
        assert response.headers["Cache-Control"] == "no-store", path


@pytest.mark.parametrize("lang", ["it", "en"])
def test_direction_row_names_the_estimate(lang):
    assert FIELD_LABELS[lang]["direction"] == (
        "Direzione della stima" if lang == "it" else "Direction of the estimate"
    )


@pytest.mark.parametrize("lang", ["it", "en"])
@pytest.mark.parametrize(
    "assertion,direction,word",
    [
        ("directional", "+", {"it": "è aumentato", "en": "increased"}),
        ("directional", "-", {"it": "è diminuito", "en": "decreased"}),
        ("explicit_no_difference", None, {"it": "non hanno rilevato", "en": "reported no change"}),
        ("not_confirmed", "-", {"it": "non hanno confermato", "en": "did not confirm"}),
    ],
)
def test_a_change_without_a_group_name_is_described_from_its_times(
    lang, assertion, direction, word
):
    claim = json.loads(json.dumps(SYNTHETIC["q1-1"]["a"]["claim"]))
    claim["comparison"].update(type="within_group_change", index_group=None, reference_group=None)
    claim["comparison"].update(reference_time="baseline", outcome_time="week 12")
    claim["result"].update(assertion=assertion, estimate_direction=direction)
    sentence = str(claim_sentence(claim, lang))
    assert word[lang] in sentence and "baseline" in sentence and "week 12" in sentence
    assert ("non chiarisce" if lang == "it" else "does not establish") not in sentence
    # No time, no description: the comparison stays unclear.
    claim["comparison"].update(reference_time=None, outcome_time=None)
    assert ("non chiarisce" if lang == "it" else "does not establish") in str(
        claim_sentence(claim, lang)
    )
    # A missing direction is still not invented.
    claim["comparison"].update(reference_time="baseline")
    claim["result"].update(assertion="directional", estimate_direction=None)
    assert ("non chiarisce" if lang == "it" else "does not establish") in str(
        claim_sentence(claim, lang)
    )


@pytest.mark.parametrize("lang", ["it", "en"])
def test_practice_feedback_shows_complete_quoted_paths(cfg, lang):
    app = create_app({**cfg, "PRACTICE_ENABLED": True})
    seen = {}
    for _ in range(3):
        client = app.test_client()
        post(client, get(client), "/start")
        intro = client.get(f"/work?lang={lang}", base_url="https://localhost").data.decode()
        page = practice_page(client, intro, lang)
        sid = re.search(r'data-session="([^"]+)"', page).group(1)
        db = connect(app.config)
        item = db.execute(
            "SELECT item_id FROM assignments WHERE kind='practice' AND session_id=?", (sid,)
        ).fetchone()[0]
        db.close()
        form = Forms(page).forms["/answer"]
        form.update(path=json.dumps(SYNTHETIC[item]["expected_path"]), rationale="")
        feedback = client.post(
            f"/answer?lang={lang}",
            data=form,
            base_url="https://localhost",
            headers={"Origin": "https://localhost"},
            follow_redirects=True,
        ).data.decode()
        seen[item] = html.unescape(feedback)
    assert set(seen) == {"practice-1", "practice-2", "practice-3"}
    left, right = QUOTES[lang]
    ui = instrument_copy(lang)
    first = seen["practice-1"]
    for label in (
        ui["keywords"]["sample_size"],
        ui["no"],
        ui["problem_title"].split("? ", 1)[0] + "?",
        dict(ui["problems"])["missing_from_extraction"],
        ui["q1_relevance_title"],
        dict(ui["relevance_options"])["not_material"],
    ):
        assert f"{left}{label}{right}" in first, label
    third = seen["practice-3"]
    for label in (
        ui["q3_title"],
        dict(ui["q4_options"])["opposite"],
        ui["q5_title"],
        ui["q5_factor"],
        dict(ui["factors"])["population"],
    ):
        assert f"{left}{label}{right}" in third, label


@pytest.mark.parametrize("lang", ["it", "en"])
def test_a_field_that_does_not_concern_the_finding_is_correct_only_when_empty(lang):
    sentence = {
        "it": "per esempio la dose in uno studio su un biomarcatore, è corretto se è vuoto; "
        "è sbagliato se contiene un valore che l’abstract non riporta",
        "en": "for example the dose in a study of a biomarker, is correct if it is empty; "
        "it is wrong if it contains a value the abstract does not give",
    }[lang]
    guidelines = (ROOT / f"content/guidelines_{lang}.md").read_text()
    assert sentence in instrument_copy(lang)["q1_absence"] and sentence in guidelines
    # The earlier «Sì» for any field that does not apply is gone everywhere.
    for text in instructions(lang):
        assert not re.search("non si applica|non applicabile|does not apply", text), text


@pytest.mark.parametrize("lang", ["it", "en"])
def test_significance_box_names_the_fields_of_its_row(lang):
    ui = instrument_copy(lang)
    left, right = QUOTES[lang]
    item = SYNTHETIC["practice-1"]["a"]
    view = claim_view(item["claim"], item["article"]["study"], lang)
    rows = next(part for part in view["sections"] if part["key"] == "significance")["rows"]
    shown = {row["label"] for row in rows}
    for key in ("authors_significance", "p_value", "interval"):
        label = FIELD_LABELS[lang][key]
        assert label in shown and f"{left}{label}{right}" in ui["key_rules"]["q1_significance"]
    # The help keeps what the box does not say: the undeclared «Significant» case.
    help_text = ui["checks"]["significance"]["help"]
    assert "p < 0" not in help_text
    assert f"{left}{CODES[lang]['significant']}{right}" in help_text
