# SPDX-License-Identifier: AGPL-3.0-only
import copy
import json

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import ROOT
from app.presentation import claim_sentence, claim_view


@pytest.fixture
def pair():
    # Stable disabled training fixture: rendering unit cases must not depend on preview order.
    return next(
        item
        for item in json.loads((ROOT / "content/synthetic_items.json").read_text())
        if item["id"] == "q1-1"
    )


@pytest.mark.parametrize("lang", ["it", "en"])
@pytest.mark.parametrize(
    "comparison", ["between_group", "within_group_change", "association", "unclear"]
)
@pytest.mark.parametrize(
    "assertion", ["directional", "explicit_no_difference", "not_confirmed", "unclear"]
)
@pytest.mark.parametrize("direction", ["+", "-", "0", None])
def test_every_comparison_assertion_direction_language(
    pair, lang, comparison, assertion, direction
):
    claim = copy.deepcopy(pair["a"]["claim"])
    claim["comparison"]["type"] = comparison
    claim["result"]["assertion"] = assertion
    claim["result"]["estimate_direction"] = direction
    claim["comparison"]["reference_time"] = "baseline"
    claim["comparison"]["outcome_time"] = "week 12"
    rendered = str(claim_sentence(claim, lang))
    assert "<strong>fasting glucose</strong>" in rendered
    assert rendered.endswith(".")
    if comparison == "unclear" or assertion == "unclear":
        assert ("non chiarisce" if lang == "it" else "does not establish") in rendered
        assert "higher" not in rendered and "più alto" not in rendered
    elif assertion == "directional" and direction in ("0", None):
        assert ("non è stata estratta" if lang == "it" else "not extracted") in rendered
        assert "no difference" not in rendered and "senza differenze" not in rendered
    elif comparison == "between_group":
        assert "placebo group" in rendered
        assert "baseline" not in rendered
        if assertion == "directional":
            assert (
                ("più alto" if direction == "+" else "più basso") in rendered
                if lang == "it"
                else ("higher" if direction == "+" else "lower") in rendered
            )
            assert "increased" not in rendered and "è aumentato" not in rendered
    elif comparison == "within_group_change":
        assert "baseline" in rendered and "week 12" in rendered
        assert "placebo" not in rendered
    elif comparison == "association":
        assert "placebo" not in rendered and "baseline" not in rendered


def test_only_present_groups_and_times_are_used(pair):
    claim = copy.deepcopy(pair["a"]["claim"])
    claim["comparison"]["reference_group"] = None
    assert "does not identify both groups" in str(claim_sentence(claim, "en"))
    # The comparator text is not promoted into a group.
    assert "placebo" not in str(claim_sentence(claim, "en"))
    claim["comparison"]["type"] = "within_group_change"
    claim["comparison"]["reference_time"] = None
    claim["comparison"]["outcome_time"] = None
    sentence = str(claim_sentence(claim, "en"))
    assert "baseline" not in sentence and "week 12" not in sentence
    assert "placebo" not in sentence


def test_significance_preserves_target_and_does_not_calculate(pair):
    claim = copy.deepcopy(pair["a"]["claim"])
    claim["result"]["p_value"] = None
    claim["result"]["confidence_interval"]["target"] = "treatment × time interaction"
    claim["result"]["authors_significance"] = "not_reported"
    claim["result"]["significance_wording"] = None
    study = pair["a"]["article"]["study"]
    rendered = claim_view(claim, study, "en")
    stats = next(
        section["rows"] for section in rendered["sections"] if section["key"] == "significance"
    )
    by_label = {row["key"]: row["value"] for row in stats}
    assert by_label["p_value"] == "Not extracted"
    assert by_label["authors_significance"] == "Not reported"
    assert (
        next(row["target"] for row in stats if row["key"] == "interval")
        == "treatment × time interaction"
    )
    assert "target" not in by_label
    assert by_label["significance_wording"] == "Not extracted"
    assert "statistically significant" not in str(rendered["sentence"])


@pytest.mark.parametrize("lang", ["it", "en"])
def test_all_seven_groups_and_missing_counts_remain_visible(pair, lang):
    claim = pair["a"]["claim"]
    claim["comparison"]["index_group"]["n"] = None
    claim["context"]["region"] = None
    claim["analysis"]["covariates"] = ["body mass index"]
    claim["subgroup"] = {"description": "women aged 40–60", "evidence": []}
    rendered = claim_view(claim, pair["a"]["article"]["study"], lang)
    assert [section["key"] for section in rendered["sections"]] == [
        "result",
        "groups",
        "sample_size",
        "comparison",
        "analysis",
        "significance",
        "context",
    ]
    numbers = rendered["sections"][2]["rows"]
    assert numbers[1]["value"] == ("Non estratto" if lang == "it" else "Not extracted")
    assert "women aged 40–60" in str(rendered["sections"][1])
    assert "body mass index" in str(rendered["sections"][4])
    assert "body mass index" not in str(rendered["sections"][1])
    assert rendered["sections"][-1]["rows"][0]["value"] == (
        "Non estratto" if lang == "it" else "Not extracted"
    )


def test_template_escapes_all_source_text_and_raw_json(pair):
    pair["a"]["article"]["title"] = "<script>bad()</script>"
    pair["a"]["claim"]["outcome"] = "<img src=x onerror=bad()>"
    pair["a"]["claim"]["analysis"]["method"] = "<svg onload=bad()>"
    env = Environment(
        loader=FileSystemLoader(ROOT / "app/templates"), autoescape=select_autoescape()
    )
    html = env.get_template("claim.html").render(
        item=pair, side="a", lang="en", claim_view=claim_view, t=lambda key, **kwargs: key
    )
    assert "<script>" not in html and "<img src=x" not in html and "<svg onload" not in html
    assert "&lt;script&gt;" in html
    assert "extracted-data" not in html and "technical-details" not in html
    view = claim_view(pair["a"]["claim"], pair["a"]["article"]["study"], "en")
    extracted = env.from_string(
        "{% from 'task_macros.html' import fields with context %}{% for section in view.sections %}{{ fields(section) }}{% endfor %}"
    ).render(view=view, lang="en")
    assert "<img src=x" not in extracted and "<svg onload" not in extracted
    assert "&lt;img src=x" in extracted and "&lt;svg onload" in extracted
    assert 'title="-"' in extracted and "lower in the study population" in extracted
    assert "prediction" not in html and "explanation_path" not in html


@pytest.mark.parametrize("lang", ["it", "en"])
def test_risk_and_singular_counts_remain_readable(pair, lang):
    from app.presentation import count_text

    claim = pair["a"]["claim"]
    claim["kind"] = "risk"
    claim["outcome"] = "diabetes"
    sentence = str(claim_sentence(claim, lang))
    assert (
        "rischio di <strong>diabetes</strong>"
        if lang == "it"
        else "risk of <strong>diabetes</strong>"
    ) in sentence
    count = {"value": 1, "unit": "participants", "scope": "analysed", "reported_text": ""}
    assert count_text(count, lang) == (
        "1 partecipante analizzato" if lang == "it" else "1 participant analysed"
    )


@pytest.mark.parametrize("lang", ["it", "en"])
@pytest.mark.parametrize("comparison", ["between_group", "within_group_change", "association"])
def test_direction_details_do_not_imply_a_change_in_exposure(pair, lang, comparison):
    claim = pair["a"]["claim"]
    claim["comparison"]["type"] = comparison
    claim["comparison"]["orientation_text"] = "index relative to reference"
    for direction in ("+", "-"):
        claim["result"]["estimate_direction"] = direction
        rendered = claim_view(claim, pair["a"]["article"]["study"], lang)
        technical = rendered["technical"]
        label = next(row["value"] for row in technical if row["label"] == "estimate_direction")
        assert "exposure" not in label and "esposizione" not in label
        assert (
            ("higher" if direction == "+" else "lower") in label
            if lang == "en"
            else ("più alto" if direction == "+" else "più basso") in label
        )
        assert any(row["value"] == "index relative to reference" for row in technical)


@pytest.mark.parametrize("lang", ["it", "en"])
def test_statistical_text_does_not_hide_disagreeing_extracted_numbers(pair, lang):
    claim = pair["a"]["claim"]
    claim["result"]["p_value"].update(operator="<", value=0.001, reported_text="p = 0.20")
    claim["result"]["confidence_interval"].update(
        level=90, lower=1, upper=5, reported_text="95% CI -3 to -1"
    )
    rendered = claim_view(claim, pair["a"]["article"]["study"], lang)
    stats = next(
        section["rows"] for section in rendered["sections"] if section["key"] == "significance"
    )
    values = [row["value"] for row in stats]
    assert "p < 0.001" in values
    assert ("90%: da 1 a 5" if lang == "it" else "90%: from 1 to 5") in values
    assert next(row["reported"] for row in stats if row["key"] == "p_value") == "p = 0.20"
    assert next(row["reported"] for row in stats if row["key"] == "interval") == "95% CI -3 to -1"


@pytest.mark.parametrize("lang", ["it", "en"])
def test_reported_count_wording_does_not_hide_missing_structured_count(pair, lang):
    count = pair["a"]["article"]["study"]["total_n"]
    count.update(value=None, reported_text="88 participants")
    rendered = claim_view(pair["a"]["claim"], pair["a"]["article"]["study"], lang)
    numbers = next(
        section["rows"] for section in rendered["sections"] if section["key"] == "sample_size"
    )
    assert numbers[0]["value"].startswith("Non estratto" if lang == "it" else "Not extracted")
    assert numbers[0]["reported"] == "88 participants"
