# SPDX-License-Identifier: AGPL-3.0-only
"""Clarified wording, empty checks and the comparison framing on the unchanged 2.0 answer paths."""

import copy
import html
import json
import re

import pytest
from test_web import Forms, create_app, get, post

from app.config import ROOT
from app.db import connect
from app.instrument import FIELDS, instrument_copy
from app.presentation import claim_view

SYNTHETIC = {i["id"]: i for i in json.loads((ROOT / "content/synthetic_items.json").read_text())}

TEXTS = {
    "it": {
        "relevance_help": "Qui per risultato si intende ciò che l’estrazione dice di aver osservato in un abstract, non il giudizio sul confronto tra i due studi.",
        "notice": "Nella riga «Risultato» hai segnato un errore che di solito cambia il risultato. Ricontrolla: se l’estrazione riporta un risultato diverso da quello dell’abstract, scegli «Sì, cambia il risultato o il confronto».",
        "result_example": "Se l’abstract riporta un livello più basso e l’estrazione dice più alto, scegli «No» e, alla domanda «Qual è il problema?», «Direzione del risultato invertita». Se l’abstract riporta un’associazione o una differenza significativa e l’estrazione dice che non c’è, scegli «No» e, alla stessa domanda, «L’abstract non lo sostiene».",
        "exposure_example": "La stessa sostanza misurata nel siero in uno studio e nel plasma nell’altro è la stessa esposizione: se la differenza di materiale conta e i risultati sono opposti, indicala nell’ultima domanda.",
        "q2_help": "Popolazioni o metodi diversi non bastano da soli a rendere i risultati non confrontabili: scegli «No» solo se i due risultati rispondono a domande diverse. Se la domanda è la stessa, scegli «Sì»; se poi i risultati sono opposti, potrai indicare la differenza nella domanda finale. Se uno studio trova l’effetto e l’altro no, i risultati restano confrontabili.",
        "old_q2_help": "Popolazioni o metodi diversi possono comunque essere confrontabili.",
        "q2_frame": "Ora confronti i due risultati. L’estrazione ti indica quali risultati confrontare; per rispondere usa ciò che riportano gli abstract, anche dove l’estrazione è incompleta. Gli errori dell’estrazione li hai già segnalati nella parte precedente.",
        "quoted": "«{}»",
    },
    "en": {
        "relevance_help": "Here the finding means what the extraction says was observed in one abstract, not your judgement on the comparison of the two studies.",
        "notice": "In the “Finding” row you marked an error that usually changes the finding. Check again: if the extraction reports a different finding from the abstract, choose “Yes, it changes the finding or the comparison”.",
        "result_example": "If the abstract reports a lower level but the extraction says higher, choose “No” and, at the question “What is wrong?”, “Wrong direction”. If the abstract reports a significant association or difference and the extraction says there is none, choose “No” and, at the same question, “Not supported by the abstract”.",
        "exposure_example": "The same substance measured in serum in one study and in plasma in the other is the same exposure: if the difference in material matters and the findings are opposite, report it in the last question.",
        "q2_help": "Different populations or methods alone do not make the findings non-comparable: choose “No” only if the two findings answer different questions. If the question is the same, choose “Yes”; if the findings then turn out to be opposite, you can report the difference in the final question. If one study finds the effect and the other does not, the findings remain comparable.",
        "old_q2_help": "Different populations or methods may still be comparable.",
        "q2_frame": "Now compare the two findings. The extraction tells you which findings to compare; to answer, use what the abstracts report, even where the extraction is incomplete. You have already reported extraction errors in the previous part.",
        "quoted": "“{}”",
    },
}


@pytest.mark.parametrize("lang", ["it", "en"])
def test_clarified_wording(lang):
    ui, text = instrument_copy(lang), TEXTS[lang]
    assert ui["q1_relevance_help"].endswith(" " + text["relevance_help"])
    assert ui["relevance_notice"] == text["notice"]
    assert ui["checks"]["result"]["example"] == text["result_example"]
    # The example names the not_supported_by_abstract choice exactly as it is shown.
    label = dict(ui["problems"])["not_supported_by_abstract"]
    assert text["quoted"].format(label) in ui["checks"]["result"]["example"]
    assert ui["examples"]["q2_exposure"].endswith(" " + text["exposure_example"])
    assert text["q2_help"] in ui["q2_help"] and text["old_q2_help"] not in ui["q2_help"]
    assert ui["q2_frame"] == text["q2_frame"]
    # «esito» names the measured variable only, never a result.
    if lang == "it":
        for value in (
            ui["relevance_notice"],
            ui["q1_relevance_help"],
            ui["q2_help"],
            ui["q2_frame"],
        ):
            assert "esito" not in value


def section(view, key):
    return next(part for part in view["sections"] if part["key"] == key)


def test_empty_checks_are_derived_from_the_claim_data():
    item = SYNTHETIC["practice-1"]
    a = claim_view(item["a"]["claim"], item["a"]["article"]["study"], "it")
    b = claim_view(item["b"]["claim"], item["b"]["article"]["study"], "en")
    # A: no number at all. B: one group size is extracted, so all problems stay available.
    assert section(a, "sample_size")["empty"] and not section(b, "sample_size")["empty"]
    assert section(b, "context")["empty"] and not section(a, "context")["empty"]

    claim = copy.deepcopy(item["b"]["claim"])
    study = copy.deepcopy(item["b"]["article"]["study"])
    claim["comparison"].update(
        type=None,
        comparator=None,
        reference_time=None,
        outcome_time=None,
        orientation_text=None,
        index_group=None,
        reference_group=None,
    )
    claim["subgroup"] = None
    claim["analysis"].update(
        method=None, adjustment="not_reported", covariates=None, analysis_population=None
    )
    study.update(design=None, aims_reported=None, total_n=None)
    claim["result"].update(
        estimate=None,
        p_value=None,
        confidence_interval=None,
        significance_wording=None,
        authors_significance="not_reported",
        hedged=None,
        authors_trend_wording=None,
    )
    view = claim_view(claim, study, "it")
    # Not extracted and Not reported are both empty; the finding sentence never is.
    assert [part["key"] for part in view["sections"] if not part["empty"]] == ["result"]

    # Anything extracted beside a missing value keeps every problem available.
    changed = copy.deepcopy(study)
    changed["total_n"] = {
        "value": None,
        "unit": "not_reported",
        "scope": "not_reported",
        "reported_text": "about two hundred adults",
    }
    assert not section(claim_view(claim, changed, "it"), "sample_size")["empty"]
    changed["total_n"] = {"value": None, "unit": "participants", "scope": "enrolled"}
    assert not section(claim_view(claim, changed, "it"), "sample_size")["empty"]
    changed["total_n"] = {"value": None, "unit": "not_reported", "scope": "not_reported"}
    assert section(claim_view(claim, changed, "it"), "sample_size")["empty"]
    typed = copy.deepcopy(claim)
    typed["comparison"]["type"] = "association"
    assert not section(claim_view(typed, study, "it"), "comparison")["empty"]
    cases = copy.deepcopy(claim)
    cases["comparison"]["index_group"] = {"label": None, "role": "case"}
    assert not section(claim_view(cases, study, "it"), "groups")["empty"]
    region = copy.deepcopy(claim)
    region["context"] = {"region": "Italy", "duration": None, "dose": None, "sample": None}
    assert not section(claim_view(region, study, "it"), "context")["empty"]


@pytest.mark.parametrize("lang", ["it", "en"])
def test_pair_page_marks_empty_checks_and_carries_the_notice(cfg, lang):
    app = create_app({**cfg, "PRACTICE_ENABLED": True})
    client = app.test_client()
    intro = post(client, get(client), "/start")
    page = client.post(
        f"/practice-begin?lang={lang}",
        data=Forms(intro.data).forms["/practice-begin"],
        base_url="https://localhost",
        headers={"Origin": "https://localhost"},
        follow_redirects=True,
    ).data.decode()
    db = connect(app.config)
    item = SYNTHETIC[
        db.execute("SELECT item_id FROM assignments WHERE kind='practice'").fetchone()[0]
    ]
    db.close()
    tags = dict(re.findall(r'<section class="task-step" data-step="(q1\.[ab]\.\w+)"([^>]*)>', page))
    assert len(tags) == 2 * len(FIELDS)
    marked = 0
    for side in ("a", "b"):
        view = claim_view(item[side]["claim"], item[side]["article"]["study"], lang)
        for field in FIELDS:
            empty = section(view, field)["empty"]
            assert ("data-empty-check" in tags[f"q1.{side}.{field}"]) == empty, (side, field)
            marked += empty
    # The practice pairs all have at least one empty check; the finding is never empty.
    assert marked and "data-empty-check" not in tags["q1.a.result"] + tags["q1.b.result"]
    notice = re.search(r'<p class="relevance-notice"[^>]*>', page).group(0)
    assert 'role="status"' in notice and " hidden" in notice
    data = html.unescape(re.search(r'data-notice="([^"]*)"', notice).group(1))
    assert data == instrument_copy(lang)["relevance_notice"]
    # The notice stays inside the relevance step, after its options.
    relevance = page.split('data-step="q1.relevance"', 1)[1].split("</section>", 1)[0]
    assert relevance.index('name="q1.relevance"') < relevance.index("relevance-notice")
    # The comparison stage opens with one framing line, before its first question.
    frame = f'<p class="q2-framing">{html.escape(instrument_copy(lang)["q2_frame"], False)}</p>'
    assert page.count('class="q2-framing"') == 1
    exposure = page.split('data-step="q2.exposure"', 1)[1].split("</section>", 1)[0]
    assert frame in exposure and exposure.index(frame) < exposure.index("question-heading")
