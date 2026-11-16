# SPDX-License-Identifier: AGPL-3.0-only
"""The instrument is an analysis contract: exercise its branches and invalid edges."""

import copy
import itertools
import json

import pytest

from app.instrument import (
    COPY,
    DISPLAY_ORDER,
    FIELDS,
    INSTRUMENT_VERSION,
    make_path,
    parse_answer,
    validate_path,
)


def form(path, **extra):
    return {"path": json.dumps(path), **extra}


@pytest.mark.parametrize(
    ("label", "factor", "binary"),
    [
        ("extraction_error", "none", False),
        ("not_comparable", "outcome_definition", False),
        ("concordant", "none", False),
        ("not_replicated", "none", True),
        ("apparent_contradiction", "population", True),
        ("contradictory", "none", True),
    ],
)
def test_six_terminals_are_derived_not_trusted(label, factor, binary):
    result = parse_answer(form(make_path(label), label="forged", factor="forged"))
    assert (result["label"], result["factor"], result["binary_inconsistent"]) == (
        label,
        factor,
        binary,
    )
    assert result["instrument_version"] == INSTRUMENT_VERSION
    assert validate_path(result["path"]) == result


@pytest.mark.parametrize("side,field", list(itertools.product(("a", "b"), FIELDS)))
def test_every_q1_row_is_required_even_when_no_detail_is_extracted(side, field):
    path = make_path("concordant")
    del path["q1"][side][field]
    with pytest.raises(ValueError):
        validate_path(path)


@pytest.mark.parametrize("side,field", list(itertools.product(("a", "b"), FIELDS)))
def test_supporting_errors_are_diagnostics_not_pair_errors(side, field):
    path = make_path("concordant")
    path["q1"][side][field] = {"answer": "no", "problems": ["missing_from_extraction"]}
    path["q1_relevance"] = "not_material"
    result = validate_path(path)
    assert result["label"] == "concordant"
    assert result["field_problems"][side][field]["problems"] == ["missing_from_extraction"]
    assert result["relevance"] == "not_material"


def test_identified_material_error_wins_over_other_side_uncertainty():
    path = make_path("extraction_error")
    path["q1"]["b"]["groups"] = {"answer": "cannot_tell", "problems": []}
    result = validate_path(path)
    assert (result["label"], result["factor"]) == ("extraction_error", "none")
    assert result["field_problems"]["a"]["result"]["problems"] == ["wrong_direction"]
    assert result["field_problems"]["b"]["groups"]["answer"] == "cannot_tell"


def test_uncertainty_is_not_an_identified_extraction_error():
    path = {"q1": make_path("concordant")["q1"], "q1_relevance": "cannot_establish_comparison"}
    path["q1"]["a"]["result"]["answer"] = "cannot_tell"
    result = validate_path(path)
    assert (result["label"], result["factor"]) == ("not_comparable", "unknown")
    path["q1_relevance"] = "material"
    with pytest.raises(ValueError):
        validate_path(path)


def test_supporting_uncertainty_can_continue_to_comparison():
    path = make_path("contradictory")
    path["q1"]["a"]["sample_size"]["answer"] = "cannot_tell"
    path["q1_relevance"] = "not_material"
    assert validate_path(path)["label"] == "contradictory"


@pytest.mark.parametrize(
    "problems",
    [
        [],
        ["wrong_direction"],
        ["not_supported_by_abstract", "not_supported_by_abstract"],
        ["invented"],
    ],
)
def test_no_requires_at_least_one_appropriate_problem(problems):
    path = make_path("concordant")
    path["q1"]["a"]["sample_size"] = {"answer": "no", "problems": problems}
    path["q1_relevance"] = "not_material"
    with pytest.raises(ValueError):
        validate_path(path)


@pytest.mark.parametrize("answer", ["yes", "cannot_tell"])
def test_non_no_cannot_carry_error_choices(answer):
    path = make_path("concordant")
    path["q1"]["b"]["result"] = {"answer": answer, "problems": ["not_supported_by_abstract"]}
    with pytest.raises(ValueError):
        validate_path(path)


def test_multiple_result_problems_are_retained_in_stable_order():
    path = make_path("extraction_error")
    path["q1"]["a"]["result"]["problems"] = [
        "planned_as_observed",
        "not_supported_by_abstract",
        "wrong_exposure_outcome",
    ]
    assert validate_path(path)["field_problems"]["a"]["result"]["problems"] == [
        "not_supported_by_abstract",
        "wrong_exposure_outcome",
        "planned_as_observed",
    ]


@pytest.mark.parametrize("answers", list(itertools.product(("yes", "no", "cannot_tell"), repeat=3)))
def test_q2_every_answer_combination_retains_diagnostics(answers):
    path = make_path("concordant")
    failures = []
    for field, answer in zip(("exposure", "outcome", "comparison"), answers, strict=True):
        row = {"answer": answer}
        if answer == "no":
            row["reason"] = {
                "exposure": "different_exposure",
                "outcome": "outcome_definition",
                "comparison": "comparator",
            }[field]
        path["q2"][field] = row
        if answer != "yes":
            failures.append(field)
    if failures:
        del path["q3"]
        path["q2_primary"] = failures[-1]
    result = validate_path(path)
    assert result["label"] == ("not_comparable" if failures else "concordant")
    assert result["path"]["q2"] == path["q2"]
    if failures:
        expected = (
            "unknown"
            if path["q2"][failures[-1]]["answer"] == "cannot_tell"
            else {"exposure": "other", "outcome": "outcome_definition", "comparison": "comparator"}[
                failures[-1]
            ]
        )
        assert result["factor"] == expected


def test_q2_multiple_failures_require_a_decisive_reason():
    path = make_path("not_comparable")
    path["q2"]["exposure"] = {"answer": "cannot_tell"}
    del path["q2_primary"]
    with pytest.raises(ValueError):
        validate_path(path)
    path["q2_primary"] = "comparison"
    with pytest.raises(ValueError):
        validate_path(path)


@pytest.mark.parametrize(
    "reason,expected,detail",
    [
        ("different_exposure", "other", "different_exposure"),
        ("molecule_class", "molecule_class", ""),
    ],
)
def test_different_exposure_has_explicit_legacy_detail(reason, expected, detail):
    path = make_path("concordant")
    del path["q3"]
    path["q2"]["exposure"] = {"answer": "no", "reason": reason}
    result = validate_path(path)
    assert (result["factor"], result["other_detail"]) == (expected, detail)


@pytest.mark.parametrize("branch", ["q3", "q4", "q5"])
def test_uncertainty_at_every_late_branch_is_not_comparable(branch):
    path = make_path("contradictory")
    if branch == "q3":
        path["q3"] = "cannot_tell"
        del path["q4"], path["q5"]
    elif branch == "q4":
        path["q4"] = "insufficient"
        del path["q5"]
    else:
        path["q5"] = {"answer": "cannot_tell"}
    result = validate_path(path)
    assert (result["label"], result["factor"]) == ("not_comparable", "unknown")


def test_q4_size_only_corrects_q3_without_extra_question():
    path = make_path("not_replicated")
    path["q4"] = "size_only"
    assert validate_path(path)["label"] == "concordant"


@pytest.mark.parametrize("difference", ["missing_context", "cannot_determine"])
def test_q5_missing_essential_context_is_not_direct_contradiction(difference):
    path = make_path("apparent_contradiction", difference)
    result = validate_path(path)
    assert (result["label"], result["factor"]) == ("not_comparable", "unknown")


@pytest.mark.parametrize(
    "difference,factor,detail",
    [
        ("biological_sample", "sample", ""),
        ("sample_size", "other", "sample_size"),
        ("statistical_analysis", "other", "statistical_analysis"),
        ("other", "other", "Different fasting conditions"),
    ],
)
def test_q5_sample_size_never_maps_to_biological_sample(difference, factor, detail):
    path = make_path("apparent_contradiction", difference)
    if difference == "other":
        path["q5"]["detail"] = detail
    result = validate_path(path)
    assert (result["factor"], result["other_detail"]) == (factor, detail)


def test_old_ambiguous_codes_are_rejected():
    for key, old in (("factor", "sample"),):
        path = make_path("apparent_contradiction", "population")
        path["q5"][key] = old
        with pytest.raises(ValueError):
            validate_path(path)


def test_other_requires_a_short_explanation():
    path = make_path("apparent_contradiction", "other")
    for invalid in (None, "", "  ", "a" * 201):
        path["q5"]["detail"] = invalid
        with pytest.raises(ValueError):
            validate_path(path)


@pytest.mark.parametrize(
    "label", ["extraction_error", "not_comparable", "concordant", "not_replicated"]
)
def test_obsolete_downstream_choices_are_rejected(label):
    path = make_path(label)
    path["q5"] = {"answer": "no"}
    with pytest.raises(ValueError):
        validate_path(path)


def test_direct_contradiction_requires_comparability_and_no_factor():
    path = make_path("contradictory")
    path["q5"]["factor"] = "population"
    with pytest.raises(ValueError):
        validate_path(path)
    path = make_path("contradictory")
    path["q2"]["comparison"] = {"answer": "cannot_tell"}
    with pytest.raises(ValueError):
        validate_path(path)


@pytest.mark.parametrize("raw", ["", "[]", "null", "true", "{}", "{", "x" * 14001])
def test_bad_or_incomplete_wire_payloads_are_rejected(raw):
    with pytest.raises(ValueError):
        parse_answer({"path": raw})


def test_contract_rejects_unknown_rows_and_additional_properties():
    path = make_path("concordant")
    path["q1"]["a"]["invented"] = {"answer": "yes", "problems": []}
    with pytest.raises(ValueError):
        validate_path(path)
    path = make_path("concordant")
    path["q2"]["outcome"]["reason"] = "outcome_definition"
    with pytest.raises(ValueError):
        validate_path(path)


def test_note_is_optional_and_is_not_used_to_derive_label():
    path = make_path("concordant")
    result = parse_answer(form(path, rationale="  A useful note.  "))
    assert result["rationale"] == "A useful note."
    assert result["label"] == "concordant"
    with pytest.raises(ValueError):
        parse_answer(form(path, rationale="a" * 1501))


def test_languages_have_exactly_the_same_choices_and_seven_rows():
    assert COPY["it"].keys() == COPY["en"].keys()
    for key in (
        "rows",
        "problems",
        "relevance_options",
        "q2_rows",
        "exposure_reasons",
        "q4_options",
        "factors",
    ):
        assert [x[0] for x in COPY["it"][key]] == [x[0] for x in COPY["en"][key]]
    assert sorted(x[0] for x in COPY["en"]["rows"]) == sorted(FIELDS)
    assert [x[0] for x in COPY["en"]["rows"]] == list(DISPLAY_ORDER)


def test_unrelated_mutation_does_not_share_fixture_paths():
    path = make_path("concordant")
    original = copy.deepcopy(path)
    result = validate_path(path)
    result["path"]["q1"]["a"]["result"]["problems"].append("not_supported_by_abstract")
    assert path == original
