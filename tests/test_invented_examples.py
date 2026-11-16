# SPDX-License-Identifier: AGPL-3.0-only
"""Content safeguards for the invented practice and preview examples."""

import hashlib
import json
import re
from pathlib import Path

from app.instrument import validate_path
from app.package import validate_item
from scripts.check_example_originality import has_ambiguous_name_digit

ROOT = Path(__file__).resolve().parents[1]


def practices():
    return [
        item
        for item in json.loads((ROOT / "content/synthetic_items.json").read_text())
        if item["group"] == "practice"
    ]


def check_examples(items):
    titles, abstracts = set(), []
    for item in items:
        validate_item(
            {key: item[key] for key in ("item_id", "task", "arm", "a", "b")}, synthetic=True
        )
        for side in ("a", "b"):
            article, claim = item[side]["article"], item[side]["claim"]
            assert article["pmid"] is None and article["url"] is None
            assert article["title"] not in titles
            titles.add(article["title"])
            assert 180 <= len(article["abstract"].split()) <= 280
            assert all(row["text"] in article["abstract"] for row in article["sentences"])
            names = [article["title"], claim["exposure"], claim["exposure_class"], claim["outcome"]]
            for group in ("index_group", "reference_group"):
                if claim["comparison"][group]:
                    names.extend(claim["comparison"][group][key] for key in ("label", "population"))
            assert not any(has_ambiguous_name_digit(name) for name in names if name)
            words = re.findall(r"[a-z]+(?:'[a-z]+)?|\d+(?:\.\d+)?", article["abstract"].lower())
            abstracts.append({tuple(words[i : i + 8]) for i in range(len(words) - 7)})
    for index, grams in enumerate(abstracts):
        assert all(not grams.intersection(other) for other in abstracts[index + 1 :])


def test_practice_realism_and_distinct_prose():
    check_examples(practices())


def test_practice_paths_and_plain_bilingual_sentence_explanations():
    items = practices()
    assert [item["answer"] for item in items] == [
        "concordant",
        "not_replicated",
        "apparent_contradiction",
    ]
    for item in items:
        assert validate_path(item["expected_path"])["label"] == item["answer"]
        assert item["correct_path"] == item["expected_path"]
        for lang in ("it", "en"):
            explanation = item["explanation"][lang]
            assert re.search("frase|frasi" if lang == "it" else "sentence", explanation)
            assert not re.search(r"\bQ[1-5]\b", explanation + str(item["explanation_path"][lang]))
    first = items[0]
    assert first["expected_path"]["q1"]["a"]["sample_size"] == {
        "answer": "no",
        "problems": ["missing_from_extraction"],
    }
    assert first["expected_path"]["q1_relevance"] == "not_material"
    assert first["a"]["article"]["study"]["total_n"] is None
    assert all(
        item[side]["article"]["study"]["aims_reported"] for item in items for side in ("a", "b")
    )


def test_preview_truth_coverage_errors_and_no_copy():
    from collections import Counter

    from app.package import load_pairs

    items, manifest = load_pairs(ROOT / "content/preview_pairs.jsonl", preview=True)
    check_examples(items + practices())
    assert len(items) == 24
    assert Counter(item["arm"] for item in items) == {"biomarker": 8, "diet": 8, "drug": 8}
    truth = json.loads((ROOT / "docs/preview-truth.json").read_text())
    assert truth["private"] and truth["instrument_version"] == "2.0"
    assert truth["package_sha256"] == manifest["package_sha256"]
    assert {row["item_id"] for row in truth["pairs"]} == {item["item_id"] for item in items}
    labels, mismatches, erroneous_claims = Counter(), Counter(), set()
    supporting = material = 0
    for row in truth["pairs"]:
        expected = validate_path(row["expected_path"])
        assert expected["label"] == row["label"] and expected["factor"] == row["factor"]
        labels[expected["label"]] += 1
        if expected["label"] == "not_comparable":
            mismatches[expected["path"]["q2_primary"]] += 1
        supporting += expected["relevance"] == "not_material"
        material += expected["relevance"] == "material"
        for error in row["errors"]:
            key = (row["item_id"], error["side"])
            assert key not in erroneous_claims, "More than one intended error per extraction"
            erroneous_claims.add(key)
            check = error.get("field", error.get("check"))
            assert row["expected_path"]["q1"][error["side"]][check]["answer"] == "no"
    assert set(labels) == {
        "concordant",
        "not_replicated",
        "not_comparable",
        "apparent_contradiction",
        "contradictory",
        "extraction_error",
    }
    assert min(labels.values()) >= 2
    assert mismatches == {"exposure": 2, "outcome": 2, "comparison": 2}
    assert len(erroneous_claims) == 19  # 39.6% of 48 claims, each with one error.
    assert supporting == 15 and material == 4
    designs = " ".join(
        item[side]["article"]["study"]["design"].lower() for item in items for side in ("a", "b")
    )
    assert all(
        design in designs
        for design in (
            "randomized",
            "crossover",
            "cohort",
            "case-control",
            "cross-sectional",
            "meta-analysis",
        )
    )
    audit = json.loads((ROOT / "docs/preview-originality.json").read_text())
    assert audit["passed"] and audit["invented_abstracts"] == 54
    assert audit["corpus_records"] == 29559
    assert (
        audit["preview_file_sha256"]
        == hashlib.sha256((ROOT / "content/preview_pairs.jsonl").read_bytes()).hexdigest()
    )
    assert (
        audit["synthetic_file_sha256"]
        == hashlib.sha256((ROOT / "content/synthetic_items.json").read_bytes()).hexdigest()
    )
    assert not audit["corpus_title_matches"]
    assert not audit["corpus_eight_gram_matches"] and not audit["internal_eight_gram_matches"]


def test_private_truth_is_not_served_or_included_in_tasks(app):
    from test_web import get, post

    client = app.test_client()
    for url in ("/docs/preview-truth.json", "/preview-truth.json"):
        assert get(client, url).status_code == 404
    assert not (ROOT / "app/static/preview-truth.json").exists()
    task = post(client, get(client), "/start")
    assert b"answer-form" in task.data
    for private_field in (b"expected_path", b"preview-truth", b'"errors"', b'"correct_path"'):
        assert private_field not in task.data


def test_standard_disease_digits_do_not_look_like_numeric_group_names():
    assert not has_ambiguous_name_digit("adults with type 2 diabetes")
    assert not has_ambiguous_name_digit("Metformin in type 2 diabetes")
    assert has_ambiguous_name_digit("compound 201")
    assert has_ambiguous_name_digit("group 42")
    for item in practices() + [
        json.loads(line) for line in (ROOT / "content/preview_pairs.jsonl").read_text().splitlines()
    ]:
        for side in ("a", "b"):
            assert "type two diabetes" not in json.dumps(item[side])
