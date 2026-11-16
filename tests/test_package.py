# SPDX-License-Identifier: AGPL-3.0-only
import copy
import hashlib
import json

import pytest

from app.config import ROOT
from app.package import canonical_hash, load_pairs, validate_item


@pytest.fixture
def preview():
    return [
        json.loads(line) for line in (ROOT / "content/preview_pairs.jsonl").read_text().splitlines()
    ]


def write_package(tmp_path, items, *, source_type="synthetic", **manifest_overrides):
    path = tmp_path / "pairs.jsonl"
    payload = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items).encode()
    path.write_bytes(payload)
    manifest = {
        "pipeline_version": "2.0",
        "instrument_version": "2.0",
        "source_type": source_type,
        "file_sha256": hashlib.sha256(payload).hexdigest(),
        "site_canonical_sha256": canonical_hash(items),
        "package_sha256": canonical_hash(items),
        "source_hashes": {"test_fixture": hashlib.sha256(payload).hexdigest()},
        "configuration_sha256": canonical_hash({"test_fixture": True}),
    }
    manifest.update(manifest_overrides)
    path.with_suffix(".manifest.json").write_text(json.dumps(manifest))
    return path


def test_preview_import_is_exactly_twenty_four_distinct_blind_pairs():
    items, metadata = load_pairs(ROOT / "content/preview_pairs.jsonl", preview=True)
    assert len(items) == 24
    assert len({i["item_id"] for i in items}) == 24
    assert metadata["source_type"] == "synthetic"
    assert metadata["pipeline_version"] == "2.0"
    assert all(set(item) == {"item_id", "task", "arm", "a", "b"} for item in items)
    assert all(item[side]["article"]["pmid"] is None for item in items for side in ("a", "b"))


def test_preview_may_not_become_production_implicitly():
    with pytest.raises(ValueError, match="Production requires"):
        load_pairs(ROOT / "content/preview_pairs.jsonl")
    load_pairs(ROOT / "content/preview_pairs.jsonl", testing=True)


def test_exact_production_schema_import_and_mode_restriction(tmp_path, preview):
    item = copy.deepcopy(preview[0])
    # Schema-only artificial IDs; this fixture is never shown or shipped as source material.
    for side, pmid in (("a", "1"), ("b", "2")):
        item[side]["article"]["pmid"] = pmid
        item[side]["article"]["url"] = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    path = write_package(tmp_path, [item], source_type="production")
    result, _ = load_pairs(path)
    assert result == [item]
    with pytest.raises(ValueError, match="Preview requires"):
        load_pairs(path, preview=True)


@pytest.mark.parametrize(
    "field",
    ["prediction", "factor", "rationale", "label", "sampling_stratum", "oracle", "normalization"],
)
def test_verdicts_and_private_fields_are_rejected(preview, field):
    item = copy.deepcopy(preview[0])
    item[field] = "hidden"
    with pytest.raises(ValueError, match="Additional properties"):
        validate_item(item, synthetic=True)


def test_nested_extras_invalid_evidence_intervals_and_nonfinite(preview):
    for mutation in (
        lambda i: i["a"]["claim"].update(fields={}),
        lambda i: i["a"]["claim"]["result"]["evidence"][0].update(quote="invented quotation"),
        lambda i: i["a"]["claim"]["result"]["confidence_interval"].update(lower=999),
        lambda i: i["a"]["claim"]["result"]["estimate"].update(value=float("nan")),
        lambda i: i["a"]["article"]["sentences"][0].update(id=99),
        lambda i: i["a"]["claim"].update(arm="diet"),
    ):
        item = copy.deepcopy(preview[0])
        mutation(item)
        with pytest.raises(ValueError):
            validate_item(item, synthetic=True)


def test_duplicate_id_hash_and_version_rejected(tmp_path, preview):
    with pytest.raises(ValueError, match="Duplicate"):
        load_pairs(write_package(tmp_path, [preview[0], preview[0]]), preview=True)
    with pytest.raises(ValueError, match="byte hash"):
        load_pairs(write_package(tmp_path, preview[:1], file_sha256="0" * 64), preview=True)
    with pytest.raises(ValueError, match="version"):
        load_pairs(write_package(tmp_path, preview[:1], pipeline_version="1.0"), preview=True)


def test_all_optional_content_matches_package_schema_and_valid_paths():
    from app.instrument import validate_path

    items = json.loads((ROOT / "content/synthetic_items.json").read_text())
    assert len(items) == 23
    practices = [item for item in items if item["group"] == "practice"]
    assert len({item["answer"] for item in practices}) == 3
    for item in items:
        validate_item(
            {key: item[key] for key in ("item_id", "task", "arm", "a", "b")}, synthetic=True
        )
        assert validate_path(item["correct_path"])["label"] == item["answer"]
        assert item["explanation_path"]["it"] and item["explanation_path"]["en"]


def test_evidence_quote_accepts_only_whitespace_run_equivalence(preview):
    """Mirror the pipeline's frozen quote rule: whitespace runs may differ, nothing else."""

    def variant(edit_sentence=None, edit_quote=None):
        item = copy.deepcopy(preview[0])
        evidence = item["a"]["claim"]["result"]["evidence"][0]
        sentence = next(
            s for s in item["a"]["article"]["sentences"] if s["id"] == evidence["sentence_id"]
        )
        assert " " in evidence["quote"] and evidence["quote"] in sentence["text"]
        if edit_sentence:
            sentence["text"] = edit_sentence(sentence["text"], evidence["quote"])
        if edit_quote:
            evidence["quote"] = edit_quote(evidence["quote"])
        return item

    nbsp_source = lambda text, quote: text.replace(quote, quote.replace(" ", " ", 1))
    validate_item(variant(edit_sentence=nbsp_source), synthetic=True)
    validate_item(variant(edit_quote=lambda q: q.replace(" ", "  ", 1)), synthetic=True)
    for bad in (
        lambda q: q.swapcase(),
        lambda q: q.replace(" ", "", 1),
        lambda q: q + ".",
        lambda q: "   ",
    ):
        with pytest.raises(ValueError, match="Evidence quotation"):
            validate_item(variant(edit_quote=bad), synthetic=True)
