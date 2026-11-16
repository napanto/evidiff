# Instrument and export contract

`instrument_version=2.0`, `pipeline_version=2.0`. The versioned source of questions, choices, validation and examples is `app/instrument.py`; English and Italian have the same branches. `app/presentation.py` and `templates/claim.html` define the information displayed. The CLI `instrument --output FILE.json` exports the exact wording and canonical example paths. Examples are independent synthetic paths, never judgments of study items.

## Form wire format

`POST /answer` accepts signed `_form`, JSON `path`, optional `rationale` (1500 characters) and, only in preview, optional `comment` (2000). The complete form limit is 16 KB. Labels/factors supplied by clients do not determine the result. `parse_answer` returns the server-derived result and normalized path; `engine.submit` validates again before committing. Qualification uses this same instrument and validator.

The path object contains:

- `q1.a` and `q1.b`, each with exactly `result`, `groups`, `sample_size`, `comparison`, `analysis`, `significance`, `context`. Each has `answer=yes|no|cannot_tell` and `problems=[]`. A No requires one or more allowed field problems; Yes/uncertainty cannot carry errors.
- `q1_relevance=material|not_material|cannot_establish_comparison` only if a Q1 check is No/uncertain. Material requires an identified error and ends as extraction_error/none. Cannot-establish ends not_comparable/unknown. Supporting continues with diagnostics intact. If a known error changes the finding, the material branch has priority over uncertainty elsewhere.
- `q2.exposure`, `q2.outcome`, `q2.comparison`: answer plus reason when No. Uncertainty yields unknown; all failed checks are stored. `q2_primary` selects the decisive failed check when there are several. A single failed check supplies its own primary automatically.
- `q3=yes|no|cannot_tell`. Yes ends concordant/none; uncertainty ends not_comparable/unknown.
- `q4=effect_vs_no_effect|opposite|size_only|insufficient`. Only opposite continues. Other branches end not_replicated/none, concordant/none and not_comparable/unknown respectively.
- `q5.answer=yes|no|cannot_tell`, with `factor` on Yes and `detail` only for another difference. No ends contradictory/none; uncertainty or missing-context choices end not_comparable/unknown. A supported concrete difference ends apparent_contradiction. Statistical analysis and numerical sample size export as other with their specific detail, never biological sample.

Unexpected keys, stale downstream questions, unknown choices and missing required checks are rejected. Earlier choices reset later browser controls and the posted path. Work screens show no terminal category or system verdict. All abstracts and extracted strings are escaped.

## Export fields

`export-answers` includes real-pair rows only, excluding preview unless explicitly requested. JSONL retains nested objects; CSV serializes path/diagnostics as JSON strings. Both include:

- item ID, random session pseudonym, read ID (=assignment ID);
- instrument and pipeline versions, canonical package SHA256 and frozen site configuration SHA256;
- normalized Q1–Q5 `path`, `field_problems` by side/field, `relevance`, `other_detail`;
- derived `label`, legacy `factor`, binary inconsistency flag, optional rationale;
- assigned/submitted UTC timestamps, server-measured seconds;
- paid, replacement, surplus, excluded, quality_failed, counted and preview flags.

`counted=1` selects the earliest eligible vote per slot in the current snapshot. Programme review and quality exclusion can remove a vote without deleting it or its audit history. Preview exports always set paid=0/counted=0. No name is joined into these files; identities and payment records have a separate export.

Do not infer a consensus factor from the pair-category majority. Field-error diagnostics and completeness have different denominators from pair labels; Q1 is not an inventory of every result in an abstract. Keep answers recorded under different instrument versions separate. The oracle/fallback must use these English questions, paths, rendering and examples; shared information does not imply psychometric equivalence of human and model interaction.

## Wording and guidance

`app/guidance.py`, merged by `instrument_copy`, supplies a short row name, full question, visible how-to, full help and example for all seven Q1 checks. `checks[field].question` uses the side placeholder `{side}`. `how` and `examples` also cover Q2–Q5. Base instructions and the canonical choices/paths are retained; the validator and version 2.0 do not change. The browser’s A/B separation and expandable help are presentation state only. Practice explanation appears after the submitted practice answer, as before.

## Presentation contract

`keywords` supplies short labels for completed checks and review rows; `field_labels` supplies extracted-data labels. These additions in the shared wording export do not modify question meanings, answer codes, canonical paths or version 2.0. Original English extracted values remain visible, including disagreeing structured numbers and reported wording. Identical p-value/interval targets appear once; different targets stay with their own items. Missing values are never filled by inference.

The four-stage controller requires an explicit Continue after each question. Changing a branching choice clears only dependent answers. Review edits go directly back to review unless a newly opened branch is incomplete. Participant pages contain no protocol-number jargon or system verdict; expected answers appear only after practice/qualification submission.

## Options offered by the interface

Since 15 November 2026 the interface offers fewer choices. The validator, answer codes, step ids and version 2.0 are unchanged, so a page loaded earlier can still be submitted and every stored answer still validates and exports.

- `q2.comparison` No → «Cosa impedisce il confronto?» offers `comparator` («Gruppo di confronto»), `other` («Tipo di confronto o momento della misura», with its short description) and `outcome_definition`. The other factors stay in Q5 only. Before this change `other` meant «Un’altra differenza» and every factor was offered: split Q2 reasons by submission time and read `other_detail`.
- `q1_relevance=cannot_establish_comparison` is offered only when a Finding (`result`) or Comparison (`comparison`) row of either abstract is No or uncertain.
- A local draft or a correction prefill holding a choice the page no longer offers drops it quietly and opens the first question left unanswered; a local draft saved before this change also drops a Q2 `other` reason, because its label changed.
- The Direction row of the extracted data is labelled «Direzione della stima» / “Direction of the estimate”. A change within one group without a group name is described from its extracted times when the direction or a no-change assertion is extracted.
