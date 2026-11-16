# SPDX-License-Identifier: AGPL-3.0-only
"""Absent reference groups must not look like extraction omissions when inapplicable."""

import copy
import json

import pytest
from jinja2 import ChoiceLoader, DictLoader, Environment, FileSystemLoader, select_autoescape

from app.config import ROOT
from app.instrument import instrument_copy
from app.presentation import claim_view

NOTICE = {
    "it": "Questo tipo di risultato non ha un gruppo di confronto",
    "en": "This kind of finding has no comparison group",
}


@pytest.fixture
def pair():
    item = next(
        item
        for item in json.loads((ROOT / "content/synthetic_items.json").read_text())
        if item["id"] == "q1-1"
    )
    return copy.deepcopy(item)


@pytest.fixture
def templates():
    # Render the actual task macros without the unrelated site header/session.
    return Environment(
        loader=ChoiceLoader(
            [DictLoader({"base.html": ""}), FileSystemLoader(ROOT / "app/templates")]
        ),
        autoescape=select_autoescape(),
    )


def section(view, key):
    return next(part for part in view["sections"] if part["key"] == key)


def fields_html(templates, view, key, lang):
    return templates.from_string(
        "{% from 'task_macros.html' import fields with context %}{{ fields(section) }}"
    ).render(section=section(view, key), lang=lang)


def comparison_html(templates, pair, lang):
    page = templates.get_template("pair.html").make_module(
        {
            "item": pair,
            "lang": lang,
            "claim_view": claim_view,
            "instrument_copy": instrument_copy,
        }
    )
    return str(page.comparison_data("context"))


@pytest.mark.parametrize("lang", ["it", "en"])
@pytest.mark.parametrize("kind", ["association", "within_group_change", "between_group", "unclear"])
@pytest.mark.parametrize("has_reference", [False, True])
def test_group_and_count_panels_follow_the_extracted_comparison(
    pair, templates, lang, kind, has_reference
):
    claim = pair["a"]["claim"]
    claim["comparison"]["type"] = kind
    if not has_reference:
        claim["comparison"]["reference_group"] = None
    original = copy.deepcopy(claim)
    view = claim_view(claim, pair["a"]["article"]["study"], lang)
    inapplicable = kind in ("association", "within_group_change") and not has_reference
    assert view["no_reference_group"] is inapplicable
    for key in ("groups", "sample_size"):
        rows = section(view, key)["rows"]
        reference_rows = [row for row in rows if row["key"].startswith("reference_group_")]
        html = fields_html(templates, view, key, lang)
        # Both group slots are always shown; an inapplicable
        # reference says so in its slot instead of a note.
        assert NOTICE[lang] not in html
        assert reference_rows
        if inapplicable:
            assert all(
                not row["missing"] and row["value"].startswith(("Nessuno", "None"))
                for row in reference_rows
            )
        if has_reference:
            reference = claim["comparison"]["reference_group"]
            assert reference["label"] in html
            if key == "sample_size":
                assert str(reference["n"]["value"]) in html
        elif not inapplicable:
            assert all(row["missing"] for row in reference_rows)
            assert 'class="missing-value"' in html
    assert claim == original, "Presentation must not alter the extracted claim"


@pytest.mark.parametrize("lang", ["it", "en"])
@pytest.mark.parametrize("kind", ["association", "within_group_change"])
def test_both_single_group_findings_keep_reference_rows_out_of_comparison_table(
    pair, templates, lang, kind
):
    for side in ("a", "b"):
        pair[side]["claim"]["comparison"].update(type=kind, reference_group=None)
    html = comparison_html(templates, pair, lang)
    assert 'data-field-key="reference_group_name"' not in html
    assert 'data-field-key="reference_group_population"' not in html
    assert 'data-field-key="index_group_name"' in html


@pytest.mark.parametrize("lang", ["it", "en"])
@pytest.mark.parametrize("kind", ["association", "within_group_change"])
def test_mixed_table_explains_inapplicable_reference_without_hiding_the_other_one(
    pair, templates, lang, kind
):
    pair["a"]["claim"]["comparison"].update(type=kind, reference_group=None)
    reference = pair["b"]["claim"]["comparison"]["reference_group"]
    reference["label"] = "actual extracted reference"
    reference["population"] = "the reference population"
    html = comparison_html(templates, pair, lang)
    assert NOTICE[lang] in html
    assert "actual extracted reference" in html and "the reference population" in html
    reference_name = html.split('data-field-key="reference_group_name"', 1)[1].split("</tbody>", 1)[
        0
    ]
    assert 'class="missing-value"' not in reference_name


@pytest.mark.parametrize("lang", ["it", "en"])
def test_missing_between_group_reference_remains_a_missing_table_value(pair, templates, lang):
    pair["a"]["claim"]["comparison"].update(type="between_group", reference_group=None)
    html = comparison_html(templates, pair, lang)
    reference_name = html.split('data-field-key="reference_group_name"', 1)[1].split("</tbody>", 1)[
        0
    ]
    assert 'class="missing-value"' in reference_name
    assert NOTICE[lang] not in reference_name
