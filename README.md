# evidiff

evidiff is a small web application for collecting human judgements on pairs of
findings extracted from scientific abstracts. Each participant sees two abstracts,
checks the finding a pipeline extracted from each one against its abstract, then
answers a short series of comparison questions. The server derives the category of
the pair (concordant, contradictory, apparent contradiction, not replicated, not
comparable, or extraction error) from the answers, never from a label the
participant picks directly.

It was built to validate an automatic pipeline that finds inconsistent claims in
the literature on type 2 diabetes, obesity and metabolic syndrome, and it ships
with preview pairs and practice examples from that domain. The instrument itself
does not depend on the domain.

## What it does

- **Two languages and two layouts.** Italian and English, light and dark themes,
  phone and desktop layouts; complete numbered abstracts with the cited sentences
  highlighted.
- **A fixed instrument.** Seven checks per extracted finding (result, comparison,
  statistical evidence, study and analysis, people and groups, sample size, other
  context), shown under fixed labels that are the same for every study, followed by
  the comparison questions. The wording and the path validator live in
  `app/instrument.py`; `flask instrument --output FILE.json` exports them.
- **No accounts.** Each participant gets a personal code to resume on any device;
  the server keeps only a fingerprint of it.
- **Coverage-first assignment.** One pair at a time; pairs needing a first or second
  read come first, disagreements get a third read and three-way splits a fourth.
  Abandoned pairs are released after `STALE_MINUTES` of inactivity.
- **Quality checks.** Time per answer and agreement on shared pairs; a flagged
  session stops receiving work and a person can review the flag.
- **Corrections.** Participants can correct a submitted answer; the original stays
  recorded and both are exported.
- **Private export.** `flask export` writes a closed, hash-bound export of the
  answers for analysis (see `docs/private-export-operations.md` and
  `docs/export/`).
- **Optional compensation, off by default.** See below.

## Quick start (local preview)

Requires Python 3.11 or later and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --frozen
export SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
export PREVIEW_MODE=true
export DATABASE_PATH="$PWD/.local/preview.sqlite3"
export PAIR_FILE="$PWD/content/preview_pairs.jsonl"
export BASE_URL=http://localhost:8000
uv run flask --app 'app:create_app()' run --host 127.0.0.1 --port 8000
```

Open <http://localhost:8000>. The session cookie is `Secure`, so use `localhost`
locally and HTTPS anywhere else. In preview mode answers are not counted, and a
comment box is shown on every page.

## Configuration

All settings are environment variables with defaults in `app/config.py`; a commented
template is in `.env.example`. The main ones:

| Setting | Default | Meaning |
|---|---|---|
| `SECRET_KEY` | none (required) | Signs forms and hashes codes |
| `DATABASE_PATH` | `.local/app.sqlite3` | SQLite database of the study |
| `PAIR_FILE` | preview pairs in preview mode; otherwise required | The study package of pairs to annotate, validated against `content/package_item_schema.json`; the repository ships no study package |
| `PREVIEW_MODE` | `false` | Preview database: nothing is counted |
| `CONTACT_EMAIL` | empty | Shown in the footer and menu when set |
| `SOURCE_URL` | this repository | Source-code link in every footer (AGPL-3.0 section 13); point it at your own source if you change the code |
| `COMPENSATION_ENABLED` | `false` | See below |
| `PRACTICE_ENABLED` | `true` | A practice pair with feedback before the real pairs |
| `ELIGIBLE_PROGRAMMES` | example list | Programmes offered in the final form (JSON) |

The scientific and protocol settings are frozen in the database at its first start
(`config_sha256`); a changed value afterwards stops the start instead of silently
changing a running study.

The participant-facing texts in `content/` (landing, rules, eligibility, privacy
notice, guidelines) belong to an instance. `content/privacy_*.md` is a template with
placeholders in square brackets: replace them before running a study.

## Compensation

Compensation is **disabled by default**. With `COMPENSATION_ENABLED=false` no amount,
threshold, payout step or name field appears anywhere: home page, rules, privacy
notice, guidelines, header, finish form and final page. The finish form asks only
for programme and year, the `payments` command refuses to run, and `status` reports
reads only.

With `COMPENSATION_ENABLED=true` the site shows a rate per completed pair
(`PRICE_PER_PAIR_EUR`), a payout threshold (`MIN_PAYOUT_PAIRS`), an optional fixed fee
(`FIXED_FEE_EUR` from `FIXED_FEE_MIN_PAIRS` pairs), checks the worst case against
`BUDGET_CAP_EUR`, asks for first and last name at the end and writes a payment list
with `flask payments --output FILE.csv`. Set every amount yourself; the defaults are
zero.

The mode is frozen with the study: a database created with compensation keeps it
even if the setting is later removed, and a database created without it cannot be
switched on. Write your own privacy notice and rules for a paid study.

## Brand assets

The icons and social previews in `app/static/` are rendered from the SVG sources in
`brand/` (pure geometry, no fonts or third-party assets) by
`uv run --with pillow python scripts/make_brand_assets.py`, which needs `rsvg-convert`.

## Running in production

See `docs/DEPLOYMENT.md` for a gunicorn and reverse-proxy example.

## Tests

```sh
uv run pytest
```

Some tests are marked `unpaid` and run with compensation disabled; the others
describe a paid instance.

## License

Copyright (C) 2026 Antonio Napolitano. evidiff is free software under the GNU Affero
General Public License, version 3 (`AGPL-3.0-only`); see `LICENSE` and `NOTICE`. If you
run a modified version as a network service, you must offer its source code to its
users: every page footer links to `SOURCE_URL`, so set it to your own repository.
