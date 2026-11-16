# SPDX-License-Identifier: AGPL-3.0-only
import copy
import json
import re

import pytest
from test_web import create_app, get, post

from app.config import ROOT
from app.db import configuration_snapshot
from app.instrument import instrument_copy, make_path
from app.presentation import claim_view, feedback_explanation, feedback_view


@pytest.mark.parametrize("lang", ["it", "en"])
def test_missing_and_reported_values_keep_their_distinction(lang):
    pair = next(
        item
        for item in json.loads((ROOT / "content/synthetic_items.json").read_text())
        if item["id"] == "q1-1"
    )
    claim = pair["a"]["claim"]
    claim["result"].update(
        p_value=None,
        confidence_interval=None,
        significance_wording=None,
        authors_significance="not_reported",
    )
    view = claim_view(claim, pair["a"]["article"]["study"], lang)
    stats = next(section for section in view["sections"] if section["key"] == "significance")
    rows = {row["key"]: row for row in stats["rows"]}
    assert rows["p_value"]["missing"] and rows["authors_significance"]["missing"]
    assert rows["p_value"]["value"] != rows["authors_significance"]["value"]
    assert stats["note"] and "p-value" in stats["note"]
    assert list(rows)[:7] == [
        "estimate",
        "p_value",
        "interval",
        "target",
        "significance_wording",
        "authors_significance",
        "hedged",
    ]


@pytest.mark.parametrize("lang", ["it", "en"])
def test_case_and_control_populations_are_separate_and_target_is_not_repeated(lang):
    pair = next(
        item
        for item in json.loads((ROOT / "content/synthetic_items.json").read_text())
        if item["id"] == "q1-1"
    )
    claim = pair["a"]["claim"]
    claim["comparison"]["index_group"].update(role="case", population="cases with diabetes")
    claim["comparison"]["reference_group"].update(role="control", population="healthy controls")
    view = claim_view(claim, pair["a"]["article"]["study"], lang)
    rows = view["sections"][1]["rows"]
    # Both group panels come first under fixed headings; the role
    # stays beside the name; then the subgroup and the analysed population.
    assert [r["key"] for r in rows[:4]] == [
        "index_group_name",
        "index_group_population",
        "reference_group_name",
        "reference_group_population",
    ]
    assert rows[-1]["key"] == "analysis_population"
    assert "analysis_population" not in {r["key"] for r in view["sections"][4]["rows"]}
    groups = rows[:4]
    assert groups[0]["group"] == ("Popolazione in studio" if lang == "it" else "Study population")
    assert groups[2]["group"] == ("Gruppo di confronto" if lang == "it" else "Comparison group")
    assert groups[0]["suffix"] == ("(casi)" if lang == "it" else "(cases)")
    assert groups[2]["suffix"] == ("(controlli)" if lang == "it" else "(controls)")
    assert groups[1]["value"] == "cases with diabetes" and groups[3]["value"] == "healthy controls"
    target = next(row for row in view["sections"][5]["rows"] if row["key"] == "target")
    assert target["value"] == claim["result"]["p_value"]["target"]
    claim["result"]["confidence_interval"]["target"] = "interaction"
    changed = claim_view(claim, pair["a"]["article"]["study"], lang)
    rows = {row["key"]: row for row in changed["sections"][5]["rows"]}
    assert "target" not in rows
    assert rows["interval"]["target"] == "interaction"
    assert rows["p_value"]["target"] == claim["result"]["p_value"]["target"]


@pytest.mark.parametrize("lang", ["it", "en"])
def test_feedback_matches_by_stage_and_keeps_differences_visible(lang, synthetic):
    for item in synthetic.values():
        explanation = feedback_explanation(item["explanation"][lang])
        assert explanation and not re.search(r"\bQ[1-5]\b", explanation)
        stages = feedback_view(item["expected_path"], item["expected_path"], lang)
        assert all(not row["different"] for stage in stages for row in stage["rows"])
    changed = copy.deepcopy(make_path("concordant"))
    changed["q1"]["a"]["result"] = {"answer": "no", "problems": ["wrong_direction"]}
    changed["q1_relevance"] = "not_material"
    stages = feedback_view(json.dumps(changed), make_path("concordant"), lang)
    assert stages[0]["rows"][0]["different"]
    assert stages[0]["rows"][0]["label"] == instrument_copy(lang)["keywords"]["result"]


@pytest.mark.parametrize("enabled", [False, True])
def test_technical_details_flag_is_presentation_only(cfg, enabled):
    app = create_app({**cfg, "SHOW_TECHNICAL_DETAILS": enabled})
    assert configuration_snapshot(app.config) == configuration_snapshot(
        create_app({**cfg, "SHOW_TECHNICAL_DETAILS": not enabled}).config
    )
    client = app.test_client()
    response = post(client, get(client), "/start")
    html = response.data.decode()
    assert ('class="technical-details"' in html) == enabled
    assert ('"claim_id"' in html or "&#34;claim_id&#34;" in html) == enabled
    assert 'class="evidence-links"' not in html
    assert 'data-instrument="2.0"' in html


def test_plain_counts_preserve_units_and_missing_structured_value():
    pair = next(
        item
        for item in json.loads((ROOT / "content/synthetic_items.json").read_text())
        if item["id"] == "q1-1"
    )
    study = pair["a"]["article"]["study"]
    view = claim_view(pair["a"]["claim"], study, "it")
    count = view["sections"][2]["rows"][0]
    assert count["value"] == "302 partecipanti analizzati"
    assert count["reported"] == "302 adults for analysis"
    study["total_n"]["value"] = None
    missing = claim_view(pair["a"]["claim"], study, "it")["sections"][2]["rows"][0]
    assert missing["missing"] and missing["value"] == "Non estratto"
    assert missing["suffix"] == "partecipanti analizzati"
    assert missing["reported"] == "302 adults for analysis"
