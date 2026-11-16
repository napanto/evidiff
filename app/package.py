# SPDX-License-Identifier: AGPL-3.0-only
"""Import only blind pair items from the pipeline's public package contract.

The checked-in schema is copied verbatim from the pipeline contract. Synthetic
preview articles have no PMID/URL: those two nullable fields are the only schema
exception, never applied to a production package. A separate manifest binds the
file to its version and permitted use. No predictions or private provenance are
accepted in public items.
"""

import copy
import hashlib
import json
import math
import re
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "content/package_item_schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text())


def canonical_hash(items):
    """Site canonical package hash (also keep the byte hash for exact handoff)."""
    payload = json.dumps(items, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def pair_schema(synthetic=False):
    schema = copy.deepcopy(SCHEMA["oneOf"][0])
    if synthetic:
        for side in ("a", "b"):
            article = schema["properties"][side]["properties"]["article"]["properties"]
            article["pmid"] = {"type": "null"}
            article["url"] = {"type": "null"}
    return schema


def _walk(value):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def source_quote_matches(quote, source):
    """Match the pipeline's frozen whitespace-only rule without editing either value."""
    if not isinstance(quote, str) or not isinstance(source, str) or not quote.strip():
        return False
    return quote in source or re.sub(r"\s+", " ", quote) in re.sub(r"\s+", " ", source)


def validate_item(item, *, synthetic=False):
    error = next(Draft202012Validator(pair_schema(synthetic)).iter_errors(item), None)
    if error:
        location = ".".join(str(v) for v in error.absolute_path) or "item"
        raise ValueError(f"Invalid package at {location}: {error.message}")
    for side in ("a", "b"):
        article = item[side]["article"]
        claim = item[side]["claim"]
        if claim["arm"] != item["arm"]:
            raise ValueError("Pair and claim arms differ")
        sentences = article["sentences"]
        ids = [sentence["id"] for sentence in sentences]
        if not ids or ids != list(range(1, len(ids) + 1)):
            raise ValueError("Sentence IDs must be unique and start at 1")
        source = {sentence["id"]: sentence["text"] for sentence in sentences}
        if (
            not synthetic
            and article["url"] != f"https://pubmed.ncbi.nlm.nih.gov/{article['pmid']}/"
        ):
            raise ValueError("Article URL must match its PubMed ID")
        for value in _walk({"study": article["study"], "claim": claim}):
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("Non-finite numerical value")
            if not isinstance(value, dict):
                continue
            if set(value) == {"sentence_id", "quote"} and (
                value["sentence_id"] not in source
                or not source_quote_matches(value["quote"], source[value["sentence_id"]])
            ):
                raise ValueError("Evidence quotation does not match its source sentence")
            if value.get("confidence_interval"):
                interval = value["confidence_interval"]
                if interval["lower"] > interval["upper"]:
                    raise ValueError("Confidence interval endpoints are reversed")
    return item


def load_pairs(path, *, preview=False, testing=False):
    if not path:
        raise RuntimeError(
            "PAIR_FILE must point to the study package (see README); "
            "only PREVIEW_MODE=true falls back to the bundled preview pairs"
        )
    path = Path(path)
    payload = path.read_bytes()
    items = [json.loads(line) for line in payload.decode().splitlines() if line.strip()]
    if not items:
        raise ValueError("Empty package")
    manifest_path = path.with_suffix(".manifest.json")
    manifest = json.loads(manifest_path.read_text())
    required = {
        "pipeline_version",
        "instrument_version",
        "source_type",
        "file_sha256",
        "package_sha256",
        "source_hashes",
        "configuration_sha256",
    }
    if not required <= manifest.keys():
        raise ValueError(
            "Manifest lacks versions, source type, package hashes or source/configuration provenance"
        )
    if manifest["pipeline_version"] != "2.0" or manifest["instrument_version"] != "2.0":
        raise ValueError("Package version does not match the instrument version")
    hash_value = re.compile(r"^[0-9a-f]{64}$")
    for field in ("file_sha256", "package_sha256", "configuration_sha256"):
        if not isinstance(manifest[field], str) or not hash_value.fullmatch(manifest[field]):
            raise ValueError(f"Invalid manifest hash: {field}")
    sources = manifest["source_hashes"]
    if (
        not isinstance(sources, dict)
        or not sources
        or any(
            not isinstance(key, str)
            or not isinstance(value, str)
            or not hash_value.fullmatch(value)
            for key, value in sources.items()
        )
    ):
        raise ValueError("Invalid manifest source_hashes")
    source_type = manifest["source_type"]
    if source_type not in ("synthetic", "dev", "production"):
        raise ValueError("Unknown package source_type")
    if preview and source_type == "production":
        raise ValueError("Preview requires only synthetic or development items")
    if not preview and not testing and source_type != "production":
        raise ValueError("Production requires a frozen production package")
    byte_hash = hashlib.sha256(payload).hexdigest()
    if manifest["file_sha256"] != byte_hash:
        raise ValueError("Package byte hash differs from its manifest")
    seen = set()
    for item in items:
        validate_item(item, synthetic=source_type == "synthetic")
        if item["item_id"] in seen:
            raise ValueError("Duplicate pair ID")
        seen.add(item["item_id"])
    canonical = canonical_hash(items)
    if manifest["package_sha256"] != canonical:
        raise ValueError("Canonical package hash differs from its manifest")
    metadata = dict(manifest)
    metadata.update(
        package_sha256=canonical,
        file_sha256=byte_hash,
        site_canonical_sha256=canonical,
        item_count=len(items),
    )
    return items, metadata
