# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only originality audit. Run with python3 -I; never imports research code.

Only corpus hashes/counts and matches from the invented examples enter the report.
The complete research corpus is streamed, never copied into this repository.
"""

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def has_ambiguous_name_digit(value):
    # Conventional digits in disease names are permitted, including inside titles.
    normal = re.sub(r"\btype 2 diabetes\b", "type two diabetes", value, flags=re.IGNORECASE)
    return bool(re.search(r"\d", normal))


def tokens(text):
    return re.findall(r"[a-z]+(?:'[a-z]+)?|\d+(?:\.\d+)?", text.lower())


def windows(words, n=8):
    return (tuple(words[i : i + n]) for i in range(len(words) - n + 1))


def audit(corpus, practice_only=False):
    items = [
        item
        for item in json.loads((ROOT / "content/synthetic_items.json").read_text())
        if item["group"] == "practice"
    ]
    if not practice_only:
        items += [
            json.loads(line)
            for line in (ROOT / "content/preview_pairs.jsonl").read_text().splitlines()
            if line.strip()
        ]
    abstracts = {
        f"{item['item_id']}:{side}": item[side]["article"]["abstract"]
        for item in items
        for side in ("a", "b")
    }
    index = defaultdict(set)
    name_errors = []
    for key, text in abstracts.items():
        for window in windows(tokens(text)):
            index[window].add(key)
    internal = [
        {"words": " ".join(window), "abstracts": sorted(keys)}
        for window, keys in index.items()
        if len(keys) > 1
    ]
    for item in items:
        for side in ("a", "b"):
            article, claim = item[side]["article"], item[side]["claim"]
            fields = {"title": article["title"]}
            fields.update({key: claim[key] for key in ("exposure", "exposure_class", "outcome")})
            for group in ("index_group", "reference_group"):
                if claim["comparison"][group]:
                    fields[group] = claim["comparison"][group]["label"]
                    fields[group + ".population"] = claim["comparison"][group]["population"]
            for field, value in fields.items():
                if value and has_ambiguous_name_digit(value):
                    name_errors.append({"item": item["item_id"], "side": side, "field": field})
    title_index = {
        tuple(tokens(item[side]["article"]["title"])): f"{item['item_id']}:{side}"
        for item in items
        for side in ("a", "b")
    }
    title_matches = []
    corpus_matches = defaultdict(set)
    digest = hashlib.sha256()
    records = with_abstract = 0
    with corpus.open("rb") as source:
        for line in source:
            digest.update(line)
            if not line.strip():
                continue
            record = json.loads(line)
            records += 1
            title_key = tuple(tokens(record.get("title") or ""))
            if title_key in title_index:
                title_matches.append(title_index[title_key])
            text = record.get("abstract") or ""
            if text:
                with_abstract += 1
            for window in windows(tokens(text)):
                if window in index:
                    corpus_matches[window].update(index[window])
    report = {
        "method": "Case-folded alphabetic/numeric tokens; punctuation ignored; exact eight-token windows; zero phrase exceptions.",
        "name_rule": "No ambiguous digits in group, drug or study names; the standard disease phrase type 2 diabetes is permitted.",
        "scope": "three practice pairs"
        if practice_only
        else "three practice and twenty-four preview pairs",
        "corpus_records": records,
        "corpus_records_with_abstract": with_abstract,
        "corpus_sha256": digest.hexdigest(),
        "invented_abstracts": len(abstracts),
        "preview_file_sha256": hashlib.sha256(
            (ROOT / "content/preview_pairs.jsonl").read_bytes()
        ).hexdigest(),
        "synthetic_file_sha256": hashlib.sha256(
            (ROOT / "content/synthetic_items.json").read_bytes()
        ).hexdigest(),
        "corpus_title_matches": sorted(set(title_matches)),
        "word_counts": {key: len(text.split()) for key, text in abstracts.items()},
        "corpus_eight_gram_matches": [
            {"words": " ".join(window), "abstracts": sorted(keys)}
            for window, keys in corpus_matches.items()
        ],
        "internal_eight_gram_matches": internal,
        "digit_in_name": name_errors,
    }
    report["passed"] = not (internal or corpus_matches or name_errors or title_matches)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--practice-only", action="store_true")
    args = parser.parse_args()
    report = audit(args.corpus, args.practice_only)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("passed", "corpus_records", "invented_abstracts")}))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
