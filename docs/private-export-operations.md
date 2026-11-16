# Private analysis export operations

Tested only with synthetic temporary databases. Nothing here installs or enables a
timer, transfers data, signs a collection lock or confirms deployment.

## Command entry point and access

Use `flask --app app.private_export:create_operator_app` with the deployed site
environment. This factory registers the CLI without initializing/migrating the
database or loading pair content. The ordinary site CLI also exposes the commands,
but loading the ordinary application performs its normal startup initialization.

New commands:

- `config-snapshot --output FILE`: canonical ASCII JSON (no trailing newline),
  matching the database's `config_sha256`. A mismatch fails before writing.
- `snapshot-db --at ISO --output DIR`: timezone-aware earliest capture time,
  SQLite backup plus `snapshot.json`. Refuses before that instant. Pins one read
  transaction before backup; WAL writers can continue. The private source copy
  includes identity evidence and must be protected like the original database.
- `export --output DIR [--database SNAPSHOT_DB] --human-package-sha256 H
  --reference-revision-sha256 R --lock-file LOCK.json [--closed-at ISO]`: exact
  25-field answer rows and validated metadata including eligibility and aggregate
  demographics.

`--database` requires `snapshot.json` beside the supplied database. It opens the
snapshot with a `mode=ro` URI and `query_only=ON`. No retrospective cutoff argument
exists for a current-state export. The snapshot's actual session flags and
eligibility records are used, not today's live records. All submitted-time
comparisons use stored float epochs before formatting to UTC microseconds.
Formatting truncates sub-microsecond fractions so it never rounds an event or
snapshot forward across the closure boundary.

The immutable supplied schemas validate every row, metadata and the collection
lock. The exporter also checks canonical path derivations, provenance hashes,
lock/time order and coherent answer flags. Schema errors print a generic refusal,
never offending records. Signature verification and independent scientific/local
evaluator checks remain the study lead's responsibility.

`flag_history` is deliberately omitted: automatic and manual exclusions share
an audit action and free-text reasons are not reliable provenance for exact
manual-override counts. No unknown aggregate is reported as zero.

Programme/year are aggregates only, for unique sessions with a paid, nonsurplus
read and confirmed eligibility. Excluded or quality-failed reads remain in the
export and accepted-eligible demographic population. The payment minimum is not
an exclusion. Missing identities remain pending even if an orphan audit decision
exists; latest eligible audit decisions win by timestamp and then ID.

## Capture timing and historical limits

`--at` is the registered cutoff and the earliest allowed run time. The sidecar records
`captured_at`, the moment the read view was pinned, and `taken_at`, when the backup
completed.

`snapshot_at` equals the cutoff itself (`exact_instant: true`) only when both hold:

- the read view was pinned at most `EXACT_INSTANT_SECONDS` (300 s) after the cutoff;
- the pinned view has no audit row and no identity update after the cutoff.

Those two tables are the only routes by which exported state changes after the
fact. Answer rows are immutable and the exporter filters them by the cutoff. A
later answer cannot displace an earlier counted slot. Session flags change only
through `engine.exclude`, which always writes an audit row. Eligibility changes
only through an identity update or an audit decision. So the state the exporter
reads is the state that held at the cutoff. This covers the one or two seconds the
timer service needs to start.

Otherwise `snapshot_at` is the true capture time (`exact_instant: false`). Report
the missed exact cutoff to the study lead and never edit the sidecar.

To capture a snapshot at an exact instant, schedule `flask snapshot-db --at ...`
with your own scheduler (for example a systemd timer with `AccuracySec=1us`, no
randomized delay and `Persistent=false`). Each run needs a new destination. A
snapshot captures state; it does not close participant collection or export it.

## Final export and purge

`collection_closed` is true exactly when `--closed-at` is given and the snapshot
timestamp is at or after it. The operator fixes the closure instant and passes it here. Without it no export is closed, so identity purge stays locked.
After the complete final bundle is atomically published, the exporter records
its exact answer and metadata SHA256s in the configured live database. For a
snapshot export, only this explicit receipt step opens the live DB for writing;
the snapshot itself stays unchanged. The live pair/configuration hashes must
match the bundle. If receipt recording fails, keep the valid bundle, correct the
operator configuration and retry into a new directory. Purge remains locked.

`purge-identities --yes` refuses unless both valid final receipt hashes exist.
Verify and retain the private bundle and perform payment/retention checks before
purging. Receipts identify the latest successful final export, not a signature or
a substitute for the evaluator. Do not overwrite noon/final bundles. Files are
0600 and bundle directories 0700, written in a private temporary directory and
renamed only when complete. Existing output destinations are refused.

No free-text identity fields enter analysis output or command output. Submitted
rationales remain in the private answer file by contract and are never printed;
operators must not copy rows, pseudonyms or rationales into other tools or services.
