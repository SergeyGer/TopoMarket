# A3 acceptance contract audit (Step 3)

**Status:** audit complete; documentation-only change, no runtime behavior changed.

**Task:** `a3-contract-audit` (attempt 1), run `run_01m820c539rfqq3q84qqarbf84`.

**Audit date:** 2026-11-22 (UTC).

**Scope:** TopoMarket technical specification v2.0, Step 3 (update and recovery paths) and
acceptance check A3. Step 4/A4 material is explicitly out of scope for this run.

## 1. Specification location

### 1.1 Primary specification

The authoritative Step 3/A3 text was located in the project requirement record (not stored in
this checkout):

- **TopoMarket technical specification v2.0, "Step 3 implementation task: update and recovery
  paths (acceptance A3)"**, requirement revision 4, requirement id
  `req_01m81n2dj9r5p7wymah6r3473m` (ADP task metadata).
- Sections used: `Goal`, `Required behaviour` items 1-5, `Required tests` items 1-7,
  `Quality gates`, and `Constraints`.
- The repository-side status claim is `README.md:20` ("Step 3 ... Delivered") and the operational
  reference is `docs/REFRESH.md`.

### 1.2 Supplementary Step 3 sub-run contracts

The Step 3 work was decomposed into sub-run contracts that add detail to revision 4. These are
also project requirement/task metadata, not files in this checkout:

- Step 3a fetch layer: requirement revision 5, `req_01m81r3xfymfy04xhezrczy1bk`.
- Step 3b staged refresh/publication: requirement revision 6,
  `req_01m81ttw991cx3k1j4xjm1ehh4`.
- Step 3 sub-run acceptance text (cancelled/merged task records): tasks `fetch`, `stage`,
  `publish`, `rebuild-validate`, `cli`, `integration-docs`, `reconcile`, `storage`,
  `orchestrate`, `validate-reconcile`, and `orchestrate-publish`.

Where revision 4 and a sub-run contract differ, revision 4 is authoritative; the sub-run text is
used only to disambiguate wording and to identify an expected verification.

### 1.3 Out of scope

The current requirement record also contains **Step 4 / A4** material (requirement revision 7,
`req_01m820bzqcbg1q1kphfg7srkxr`: persistent homology, topology config, scores and CLI). It was
read only to confirm that it is the wrong step for this run. No Step 4 requirement is audited,
implemented, or used to change A3 expectations.

### 1.4 Blocker check

**No blocking ambiguity.** The Step 3/A3 specification was found and its requirements are
actionable. Two wording points are resolved by the supplementary contracts:

- "default quick refresh (FRED + Cboe)" means the default `topomarket refresh` source set is
  `fred_sp500,cboe_vix`, not all four providers (gap G-01 in §4).
- "Keep original bytes ... schema version and any upstream timestamp" means the attempt metadata
  and received payload must be reproducible from immutable provenance under the data directory,
  not merely held in a transient staging directory.

No dependent implementation task was started by this audit.

## 2. Baseline test and quality-gate result

Commands were run from the workspace root on Python 3.12.3 / pytest 8.4.2 / ruff 0.17.6.

```text
$ python -m pytest -q tests
ssssssss................................................................ [ 32%]
................................................s....................... [ 64%]
........................................................................ [ 96%]
.......                                                                  [100%]
=========================== short test summary info ============================
SKIPPED [3] tests/private_acceptance/test_private_refresh_acceptance.py:44: TOPOMARKET_SEED_DIR is not set; A3 acceptance checks are opt-in
SKIPPED [1] tests/private_acceptance/test_private_seed_acceptance.py:219: TOPOMARKET_SEED_DIR is not set; private acceptance checks are opt-in
SKIPPED [1] tests/private_acceptance/test_private_seed_acceptance.py:230: TOPOMARKET_SEED_DIR is not set; private acceptance checks are opt-in
SKIPPED [1] tests/private_acceptance/test_private_seed_acceptance.py:284: TOPOMARKET_SEED_DIR is not set; private acceptance checks are opt-in
SKIPPED [1] tests/private_acceptance/test_private_seed_acceptance.py:335: TOPOMARKET_SEED_DIR is not set; private acceptance checks are opt-in
SKIPPED [1] tests/private_acceptance/test_private_seed_acceptance.py:345: TOPOMARKET_SEED_DIR is not set; private acceptance checks are opt-in
SKIPPED [1] tests/test_private_seed.py:38: private seed environment is not configured
214 passed, 9 skipped in 10.16s
```

**Baseline result: 214 passed, 9 skipped, 0 failed.** All skips are the documented opt-in private
acceptance tests; no public test failed or errored.

Focused A3 files:

```text
$ python -m pytest -q tests/test_refresh.py tests/test_fetch.py
33 passed in 4.93s
```

Other declared Step 3 quality gates were also run for context (they are not the A3 acceptance
criterion for this audit):

```text
python -m compileall -q src tests app.py   # exit 0
python -m ruff check .                     # All checks passed!
python -m ruff format --check .            # 108 files already formatted
```

## 3. Requirement audit

Status values:

- **MET** - implementation and a public reproducible test exist.
- **PARTIAL** - core behavior exists, but a required observable, edge case, or test is missing.
- **GAP** - required behavior is not implemented or is observably wrong.

### 3.0 Goal-level surface

| ID | Requirement (abridged) | Implementation | Status and evidence |
| --- | --- | --- | --- |
| A3-0.1 | Add Data-screen/freshness information at the CLI/report layer; expose the data and hooks needed and render basic status in the existing app shell where reasonable. The full UI screen remains Step 7. | `build_overview` resolves the active snapshot directory and latest date (`src/topomarket/ui/overview.py:248-300`); `app.py:89-94` renders the latest date and data directory. | **PARTIAL / acceptable for Step 3.** Basic latest-date status is rendered and the full screen is correctly deferred to Step 7. The shell does not render per-source freshness, active snapshot id or revision counts; that belongs with the interface work in `a3-integration` (G-08). |

### 3.1 Source refresh (revision 4, §Required behaviour 1)

| ID | Requirement (abridged) | Implementation | Status and evidence |
| --- | --- | --- | --- |
| A3-1.1 | Implement `topomarket refresh` for the fixed sources; keep `topomarket import`. | `src/topomarket/cli.py:191-211`, `573-597`; `src/topomarket/data/refresh.py:719-1025`; import remains in `src/topomarket/cli.py:416-504`. | **MET.** `tests/test_refresh.py::test_cli_refresh_sources_and_validate` and the import suite exercise both paths. |
| A3-1.2 | Fixed HTTPS URLs for FRED, Cboe, French ZIP and optional OFR; OpenIntro is a fixed seed and is not refreshed. | `src/topomarket/data/fetch.py:26-36`; `src/topomarket/data/refresh.py:70-78`; OpenIntro only appears as baseline history. | **MET.** `tests/test_fetch.py::test_source_registry_matches_the_specification`; no fetch path for OpenIntro. |
| A3-1.3 | Conditional GET with a sensible fallback for providers without validators. | `src/topomarket/data/fetch.py:122-127`, `177-208`; validators are bound to the active snapshot in `refresh.py:290-307`. | **MET.** `test_conditional_headers_are_sent_only_when_validators_are_provided`, `test_304_preserves_supplied_validators_when_response_omits_them`, `tests/test_refresh.py::test_304_not_modified_keeps_the_snapshot`. |
| A3-1.4 | 15-second timeout, up to three attempts with backoff. | Defaults at `src/topomarket/data/fetch.py:96-106`; retry loop `136-228`; refresh delegates at `refresh.py:758-769`. | **MET at the fetch layer.** `test_configured_timeout_reaches_the_request`, `test_retryable_status_is_retried_then_succeeds`, `test_retry_exhaustion_keeps_final_response_metadata`, `test_timeout_is_retried_then_succeeds`. Refresh status does not persist the settings (**G-12**). |
| A3-1.5 | `--sources fred,cboe,french,ofr` selection, and a default quick refresh of FRED + Cboe. | `src/topomarket/cli.py:206-211`; `DEFAULT_REFRESH_SOURCES` is **all four** at `src/topomarket/data/refresh.py:78`. | **GAP (G-01).** The selection works, but the default is all four providers. |
| A3-1.6 | Per-source status: URL, latest observation date, last attempt time/outcome, last success, conditional-GET result; no provider secrets. | `SourceRefreshStatus` at `refresh.py:91-114`; persisted by `_write_refresh_status` (`322-340`); shown by `_show_sources` (`cli.py:600-631`). | **PARTIAL (G-02, G-12).** URL, last attempt/outcome, last success, HTTP status and `not_modified` are present; latest observation date, retry/backoff/timeout metadata are not. No credentials are accepted or sent (`fetch.py`). |
| A3-1.7 | Injectable/mockable `httpx` transport; tests must not hit the network. | `fetch_source(..., transport=...)` at `fetch.py:96-105`; refresh has an injectable `fetcher` at `refresh.py:719-725`. | **MET.** All of `tests/test_fetch.py` uses `httpx.MockTransport`; `test_injected_transport_is_not_closed_by_the_fetcher`; no live-network test exists. |

### 3.2 Staging and validation (revision 4, §Required behaviour 2)

| ID | Requirement (abridged) | Implementation | Status and evidence |
| --- | --- | --- | --- |
| A3-2.1 | Keep original bytes, SHA-256, `received_at_utc`, source id, schema version and any upstream timestamp. | Staging sidecar in `refresh.py:366-390`; staging is deleted in the `finally` at `refresh.py:1024-1025`. | **GAP (G-03).** The sidecar has source id, filename, SHA-256, size, `received_at_utc` and HTTP status, but not URL, conditional result, schema version or upstream timestamp. It is transient, and the published snapshot's `raw_hashes.json` / `parser_reports.json` are copied from the baseline rather than the refreshed bytes. |
| A3-2.2 | Validate required columns, date order, unique keys, finite values, units, archive members and the 50 MiB cap; reject absolute/traversal paths. | `_validate_archive` (`refresh.py:348-363`); `_stage_fetched_bytes` (`366-390`); adapter validation in `_build_candidate` (`393-417`); `MAX_SOURCE_BYTES` (`refresh.py:49-50`). | **PARTIAL.** Size cap, empty payload and broken ZIP are enforced (`test_oversized_payload_is_rejected`, `test_broken_archive_keeps_the_previous_snapshot`). Schema/duplicate/non-finite/date checks are too permissive (**G-05**); ZIP path checks miss drive-letter absolute and bare `..` members (**G-06**). |
| A3-2.3 | Stage conflicting duplicates, revisions and unknown schemas for review; record them in parser reports rather than silently choosing. | No conflict/quarantine path; adapters sort and merge duplicate dates in `_normalise_rows` (`normalized.py:140-167`); `_merge_sp500` overwrites by date (`refresh.py:459-474`). | **GAP (G-05, G-03).** Duplicate dates silently last-win, unknown schemas are accepted, and candidate parser reports are not written into the published snapshot. |
| A3-2.4 | New local files pass through the same adapter path. | `import_sources` is used by `topomarket import` (`cli.py:448-458`) and by `_build_candidate` (`refresh.py:393-417`). | **MET.** `tests/test_refresh.py` builds its baseline through `import_sources`; the A2 adapter suite remains green. |

### 3.3 Reconcile and publish (revision 4, §Required behaviour 3)

| ID | Requirement (abridged) | Implementation | Status and evidence |
| --- | --- | --- | --- |
| A3-3.1 | Serialize writers with one local lock. | `_RefreshLock` at `refresh.py:169-227`; acquired for the whole refresh at `737`. | **MET for the basic case.** `tests/test_refresh.py::test_concurrent_refresh_is_rejected_by_the_lock`. Stronger two-writer/no-partial-manifest coverage is missing (**G-11**). |
| A3-3.2 | Merge by source/date; retain price history outside the shorter FRED export; keep the fixed cutover; log revisions. | `_merge_sp500` (`refresh.py:459-488`), merge (`526-574`), revisions (`585-622`). | **PARTIAL.** Test `test_revised_close_and_shorter_export_retain_history` covers retention, cutover and price revisions. VIX revisions are not logged (**G-13**); conflicts are not recorded in parser reports (**G-05**). |
| A3-3.3 | Complete immutable manifest; atomic active pointer only after required inputs pass; optional OFR failure leaves its previous version available with visible status. | Snapshot build/publish `refresh.py:907-988`; `_atomic_write_json` `234-242`; import manifest `668-711`; optional failure `807-825`. | **PARTIAL.** `test_optional_source_failure_still_publishes` and `test_refresh_publishes_an_atomic_snapshot` cover the main path. Snapshot identity/history is inconsistent (**G-08**); the failed source is not always named (**G-07**); OFR previous-content retention is not directly asserted (**test gap, §3.7**). |
| A3-3.4 | Unchanged content preserves the previous snapshot id; changed content produces a new id and a revision record. | Unchanged path `refresh.py:873-905`; changed path `907-998`. | **PARTIAL.** `test_unchanged_content_preserves_the_snapshot` and `test_revised_close_and_shorter_export_retain_history` pass. A changed VIX close produces a new snapshot with **zero** revision records (**G-13**). |

### 3.4 Recompute and recover (revision 4, §Required behaviour 4)

| ID | Requirement (abridged) | Implementation | Status and evidence |
| --- | --- | --- | --- |
| A3-4.1 | Rebuild features/labels affected by revisions (full recomputation acceptable); prove a clean rebuild; if labels are absent, document the Step 6 20-session label requirement. | Normalized tables are recomputed from merged inputs (`refresh.py:851-859`); no feature/label implementation exists. | **PARTIAL (G-10).** The test compares the published tree digest to the new snapshot id (`tests/test_refresh.py:251-254`), which is tautological; it does not independently rebuild from staged inputs. `refresh.py`'s module docstring does not state the Step 6 label requirement. |
| A3-4.2 | Failed refresh/validation keeps the last good snapshot readable and surfaces failed source, last success and last attempt; never leave a partial snapshot active. | `refresh_sources` exception path `refresh.py:1000-1025`; pointer written only after the snapshot rename (`957-967`). | **PARTIAL.** `test_broken_archive_keeps_the_previous_snapshot` and `test_required_source_failure_keeps_last_good_snapshot` prove the pointer stays. When staging/validation fails before a status is appended, the failed source is missing or all sources are marked failed with a generic error (**G-07**). No injected publication-failure test exists (**G-11**). |
| A3-4.3 | Catalog/summary/report exposes active snapshot id, per-source last success/attempt, revision counts, added/removed rows. | `topomarket status` (`cli.py:355-377`), `sources` (`600-631`), `report` (`380-413`); refresh manifest contains revisions (`refresh.py:943-956`). | **GAP (G-08, G-09, G-02).** `sources` has last success/attempt, but no latest observation. `report` does not expose revision counts or added/removed rows. Refresh snapshots are not discovered as history, so `snapshot_count` is 0, and `report --profile` (without `--data-dir`) reports `active_snapshot_id: null`. |

### 3.5 CLI and reporting surface (revision 4, §Required behaviour 5)

| ID | Requirement (abridged) | Implementation | Status and evidence |
| --- | --- | --- | --- |
| A3-5.1 | `topomarket refresh [--sources ...] [--data-dir ...] [--json]`. | Parser `cli.py:191-211`; dispatch `306-311`; `_run_refresh` `573-597`. | **MET** for the options and JSON output (`test_cli_refresh_sources_and_validate`); default source set is wrong (**G-01**). |
| A3-5.2 | `topomarket sources` or extend `report`/`status` with per-source freshness, last success/attempt, refresh outcome and active snapshot. | `_show_sources` `cli.py:600-631`; `_show_status` `355-377`; `_show_report` `380-413`. | **PARTIAL.** Active snapshot and last attempt/success/outcome are present in `sources`; latest observation date is missing (**G-02**), and report/catalog state is inconsistent (**G-08**). |
| A3-5.3 | Exit codes: 0 success, 2 validation/refresh failure with a readable message, 1 unexpected. | `_run_refresh` returns 2 for `RefreshError`/`RefreshBusyError` (`cli.py:579-581`); `main` returns 2 for `OSError`/`ValueError` (`316-318`); unexpected exceptions propagate as process exit 1. | **PARTIAL.** Tests cover 0 and 2 (`test_cli_refresh_sources_and_validate`, `test_first_refresh_requires_fetched_data_not_304`); there is no reproducible test for exit 1 or for a failed refresh preserving the previous snapshot through the CLI (**G-11**). |
| A3-5.4 | `topomarket validate` validates the manifest, snapshot history and referenced normalized tables. | `_validate_data_dir` `cli.py:522-570`; `validate_data_directory` `report.py:651-751`. | **GAP (G-08).** Only the active snapshot directory is validated. `list_snapshots` (`manifest.py:851-921`) looks for `manifest.json`, while refresh snapshots contain `refresh_manifest.json`/`import_manifest.json`, so history is empty and is never checked. |

### 3.6 Required public tests (revision 4, §Required tests)

| ID | Required test | Current coverage | Status |
| --- | --- | --- | --- |
| A3-T1 | HTTP 304 keeps the current snapshot id and writes no new tables. | `tests/test_refresh.py:211-224` checks id and outcomes only. | **PARTIAL (G-11).** It does not assert that no normalized table or snapshot was created. |
| A3-T2 | Transient failures retried; exhausted retries leave the last good snapshot active and report the failed source. | Retry/timeout are unit-tested in `tests/test_fetch.py`; `test_required_source_failure_keeps_last_good_snapshot` injects an already-failed `FetchResult`. | **PARTIAL (G-07).** No refresh-level test drives a transient failure through the retry loop; the failure-reporting assertion is too weak. |
| A3-T3 | Revised old close produces a new snapshot/revision; clean rebuild hashes match. | `test_revised_close_and_shorter_export_retain_history`. | **PARTIAL (G-10).** New snapshot/revision are checked; the "clean rebuild" is not independently performed. |
| A3-T4 | Broken/truncated ZIP and unknown schema/column changes rejected; previous snapshot readable. | `test_broken_archive_keeps_the_previous_snapshot`. | **PARTIAL (G-05, G-07).** Unknown/missing columns are accepted; the broken-ZIP test passes even though the failed source is omitted from status. |
| A3-T5 | Two concurrent refresh attempts serialized; complete active manifest; no partial state. | `test_concurrent_refresh_is_rejected_by_the_lock`. | **PARTIAL (G-11).** It holds the lock in the same process and does not verify the active manifest/history after the busy result. |
| A3-T6 | Older price history survives a shorter FRED export. | `test_revised_close_and_shorter_export_retain_history` asserts the retained dates. | **MET.** Dates before the shorter export remain in `sp500_daily`. |
| A3-T7 | Clocks/metadata: `received_at_utc` and retry/backoff recorded; 15 s timeout asserted via configuration. | `test_configured_timeout_reaches_the_request`; `test_successful_fetch_uses_the_literal_provider_url`; sidecar/status timestamps. | **PARTIAL (G-12).** The fetch layer records `attempts` and `timeout_seconds`, but the refresh status drops them; `clock` does not control `refresh_status.updated_at_utc`; no test asserts recorded retry/backoff/timeout metadata. |

### 3.7 Additional Step 3 sub-run acceptance details

The Step 3 sub-run contracts add requirements that are not verbatim in revision 4 but are part of
the same Step 3 delivery. They are audited here because they remove ambiguity:

| Detail | Source | Current result |
| --- | --- | --- |
| Default refresh is FRED + Cboe. | `cli` task acceptance 1. | **GAP G-01.** |
| Source output includes each source's latest observation. | `cli` task acceptance 2. | **GAP G-02.** |
| Validate checks manifest history and tables. | `cli` task acceptance 4. | **GAP G-08.** |
| Sidecar contains source, URL, SHA-256, receipt time, HTTP status and conditional result. | `stage` task acceptance 1. | **GAP G-03** (URL, conditional result, schema/upstream data absent). |
| Unknown schemas, missing columns, invalid dates/keys/non-finite values/units rejected. | `stage`, `validate-reconcile` task acceptance. | **GAP G-05.** |
| Failed/stale staging artifacts cleaned or quarantined. | `stage`, `storage` task acceptance. | **GAP G-04.** |
| Conflicts and revisions appear in parser reports; row additions/removals counted. | `reconcile` task acceptance. | **GAP G-03/G-05/G-09.** |
| Complete snapshot and history entry before atomic pointer; readers never see partial active manifest. | `storage`, `orchestrate-publish` task acceptance. | **PARTIAL G-08/G-11.** |
| Optional OFR failure retains the previous OFR version. | `orchestrate` task acceptance. | Implementation copies previous artifacts, but no assertion on OFR rows (**test gap**). |
| Module docstring states Step 6 must rebuild labels for the 20 sessions before a revised close. | `orchestrate`, `orchestrate-publish` task acceptance. | **GAP G-10.** |
| Atomic replacement is tested against injected publication failures. | `storage`, `orchestrate-publish` task acceptance. | **GAP G-11.** |

## 4. Gap register and reproduction

Each gap below is actionable for a later Step 3 task. Reproducers use only offline fixtures and a
temporary data directory. The fixture helpers are in `tests/test_refresh.py`; run them with
`PYTHONPATH=src:tests` (the test suite sets this path through the project configuration).

### G-01 Default refresh source set diverges from the specification

- **Requirement:** revision 4 §1, "default quick refresh (FRED + Cboe)"; `cli` sub-run acceptance
  item 1.
- **Current:** `DEFAULT_REFRESH_SOURCES` is `fred_sp500,cboe_vix,french_12_industries,ofr_fsi`
  (`refresh.py:70-78`), and the CLI help says "default: all four providers"
  (`cli.py:206-211`).
- **Reproducer:**

  ```bash
  PYTHONPATH=src python -c \
    "from topomarket.data.refresh import DEFAULT_REFRESH_SOURCES; print(DEFAULT_REFRESH_SOURCES)"
  # ('fred_sp500', 'cboe_vix', 'french_12_industries', 'ofr_fsi')
  ```

- **Remaining work:** resolve how a FRED+Cboe quick refresh interacts with the required French
  source (the current all-four default avoids publishing a snapshot with an empty `tda_daily`).
  This needs a product decision and a focused CLI test; do not change it without one.

### G-02 Per-source status has no latest observation date

- **Requirement:** revision 4 §1 and §4/§5; `cli` sub-run acceptance item 2.
- **Current:** `SourceRefreshStatus` (`refresh.py:91-114`) and `refresh_status.json` contain URL,
  last attempt, last success, HTTP status and conditional result, but no latest observation date.
  `topomarket sources` (`cli.py:600-631`) prints only those fields.
- **Reproducer:**

  ```bash
  PYTHONPATH=src:tests python - <<'PY'
  from pathlib import Path
  import tempfile
  from topomarket.data.refresh import load_refresh_status, refresh_sources
  from test_refresh import _baseline, _fetcher
  root = Path(tempfile.mkdtemp()) / "data"
  _baseline(root)
  refresh_sources(root, fetcher=_fetcher())
  print(sorted(load_refresh_status(root)["sources"]["fred_sp500"]))
  # ['error', 'http_status', 'last_attempt_at', 'last_success_at',
  #  'not_modified', 'outcome', 'received_at_utc', 'source_id', 'url']
  PY
  ```

- **Remaining work:** source observation dates can come from the candidate parser reports or the
  snapshot source tables; use the refreshed candidate, not the stale baseline reports (G-03).

### G-03 Staging/provenance metadata is incomplete and not retained

- **Requirement:** revision 4 §2 first bullet; `stage` sub-run acceptance item 1; `storage`
  sub-run acceptance (immutable provenance).
- **Current:** `_stage_fetched_bytes` writes
  `{source_id, filename, sha256, size_bytes, received_at_utc, http_status}` to a sidecar
  (`refresh.py:366-390`), but the sidecar lacks URL, conditional result, schema version and
  upstream timestamp (`docs/REFRESH.md:40` already claims the URL is recorded). The whole attempt
  staging directory is removed in `finally` (`refresh.py:1024-1025`), so no original bytes remain.
  The published `raw_hashes.json` and `parser_reports.json` are copied from the previous
  snapshot/baseline, not regenerated from the refreshed payloads.
- **Reproducer** (revised FRED payload):

  ```bash
  PYTHONPATH=src:tests python - <<'PY'
  from pathlib import Path
  import hashlib, json, tempfile
  from topomarket.data.refresh import refresh_sources
  from test_refresh import _baseline, _fetcher, _bodies
  root = Path(tempfile.mkdtemp()) / "data"
  _baseline(root)
  body = (b"observation_date,SP500\n2018-12-10,250.00\n"
          b"2018-12-11,251.00\n2018-12-12,260.00\n")
  bodies = _bodies(); bodies["fred_sp500"] = body
  report = refresh_sources(root, fetcher=_fetcher(bodies))
  snap = root / "snapshots" / report.new_snapshot_id
  raw = json.loads((snap / "raw_hashes.json").read_text())["entries"]
  entry = next(item for item in raw if item.get("source_id") == "fred_sp500")
  print("candidate:", hashlib.sha256(body).hexdigest())
  print("published:", entry["sha256"])
  print("staging:", list((root / "staging").glob("*")))
  PY
  # candidate and published hashes differ; staging is empty
  ```

- **Remaining work:** persist the received bytes/metadata (or a reproducible provenance record)
  under the data directory, include URL/conditional result/schema/upstream timestamp, and
  regenerate the snapshot's raw-hash registry and parser reports from the refreshed candidates.

### G-04 Stale staging artifacts are not cleaned or quarantined

- **Requirement:** revision 4 §2/§3; `stage` and `storage` sub-run acceptance.
- **Current:** `refresh_sources` removes only the attempt directory it created
  (`refresh.py:1024-1025`). A staging directory left by a crashed process is never examined or
  cleaned.
- **Reproducer:**

  ```bash
  PYTHONPATH=src:tests python - <<'PY'
  from pathlib import Path
  import tempfile
  from topomarket.data.refresh import refresh_sources
  from test_refresh import _baseline, _fetcher
  root = Path(tempfile.mkdtemp()) / "data"
  _baseline(root)
  stale = root / "staging" / "crashed-attempt"
  stale.mkdir(parents=True); (stale / "partial.txt").write_text("x")
  refresh_sources(root, fetcher=_fetcher())
  print(sorted(p.name for p in (root / "staging").iterdir()))
  # ['crashed-attempt']
  PY
  ```

- **Remaining work:** clean/quarantine stale attempt directories before starting a refresh, and
  ensure no stale bytes can be mistaken for a candidate.

### G-05 Validation accepts unknown schemas, duplicates, non-finite values and unordered dates

- **Requirement:** revision 4 §2 second and third bullets; `stage` and `validate-reconcile`
  sub-run acceptance.
- **Current:** refresh reuses the A2 adapters. `standard_rows(single_value=True)` falls back to the
  first numeric column when a named SP500 column is absent (`adapters/base.py:1234-1242`), so a
  missing/wrong header is still accepted. Extra columns are accepted. Duplicate dates are merged
  first-wins/last-wins without a conflict record (`normalized.py:140-167`,
  `refresh.py:459-474`). Non-finite values are coerced to missing rather than rejected
  (`adapters/base.py:235-277`). Date order is sorted, not validated against the input order.
  `docs/REFRESH.md:42-43` claims empty/unknown/malformed payloads are rejected and quarantined;
  the unknown/missing-column and duplicate cases above contradict that claim.
- **Reproducer** (three payload variants; all publish):

  ```bash
  PYTHONPATH=src:tests python - <<'PY'
  from pathlib import Path
  import tempfile
  from topomarket.data.refresh import refresh_sources
  from test_refresh import _baseline, _fetcher, _bodies

  def run(label, fred):
      root = Path(tempfile.mkdtemp()) / "data"
      _baseline(root)
      bodies = _bodies(); bodies["fred_sp500"] = fred
      report = refresh_sources(root, fetcher=_fetcher(bodies))
      print(label, "published:", report.published)

  run("missing SP500 header",
      b"observation_date,WRONG\n2018-12-10,250\n2018-12-11,251\n")
  run("duplicate date",
      b"observation_date,SP500\n2018-12-10,250\n2018-12-10,251\n"
      b"2018-12-11,252\n2018-12-12,260\n")
  run("non-finite",
      b"observation_date,SP500\n2018-12-10,nan\n2018-12-11,inf\n2018-12-12,260\n")
  PY
  # all three print "published: True"
  ```

- **Remaining work:** add a refresh-level schema/contract check before publication, reject or
  quarantine unknown/missing columns and non-finite values, detect duplicate keys and record
  conflicts/revisions in parser reports. Do not weaken the existing A2 adapter contracts.

### G-06 ZIP path validation misses some absolute/traversal members

- **Requirement:** revision 4 §2; `stage` sub-run acceptance ("absolute or traversal member
  paths").
- **Current:** `_validate_archive` rejects names starting with `/`, `../`, or containing `/../`
  (`refresh.py:348-363`). It accepts `C:/evil.csv` (drive-letter absolute) and a member named
  exactly `..`.
- **Reproducer:**

  ```bash
  PYTHONPATH=src python - <<'PY'
  import io, zipfile
  from topomarket.data.refresh import _validate_archive, RefreshError
  for name in ("C:/evil.csv", "..", "a/../../evil.csv"):
      buf = io.BytesIO()
      with zipfile.ZipFile(buf, "w") as archive:
          archive.writestr(name, "data")
      try:
          _validate_archive(buf.getvalue()); print(name, "ACCEPTED")
      except RefreshError:
          print(name, "REJECTED")
  # C:/evil.csv ACCEPTED
  # .. ACCEPTED
  # a/../../evil.csv REJECTED
  PY
  ```

- **Remaining work:** reject drive-letter/absolute paths and any `..` component robustly (use
  `PurePosixPath` parts), and add a regression test for each form.

### G-07 Failed source is not surfaced when staging/validation fails

- **Requirement:** revision 4 §4 ("surface the failed source, last success and last attempt");
  `publish` and `orchestrate` sub-run acceptance; required tests 2 and 4.
- **Current:** a `SourceRefreshStatus` is appended only after `_stage_fetched_bytes` succeeds
  (`refresh.py:826-849`). If staging fails (broken ZIP, oversized payload), the failing source has
  no status entry; the exception handler (`1000-1023`) only rewrites statuses already collected.
  If validation fails later in `_build_candidate`, every source is marked `failed` with the same
  generic error. `test_broken_archive_keeps_the_previous_snapshot` asserts only that *some* source
  is failed, so it does not catch this.
- **Reproducer:**

  ```bash
  PYTHONPATH=src:tests python - <<'PY'
  from pathlib import Path
  import tempfile
  from topomarket.data.refresh import (
      RefreshError, load_refresh_status, refresh_sources,
  )
  from test_refresh import _baseline, _fetcher, _bodies
  root = Path(tempfile.mkdtemp()) / "data"
  _baseline(root)
  refresh_sources(root, fetcher=_fetcher())
  bodies = _bodies(); bodies["french_12_industries"] = b"not a zip"
  try:
      refresh_sources(root, fetcher=_fetcher(bodies))
  except RefreshError:
      pass
  status = load_refresh_status(root)["sources"]
  print({key: value["outcome"] for key, value in status.items()})
  # {'cboe_vix': 'failed', 'fred_sp500': 'failed'}  <- French source is absent
  PY
  ```

- **Remaining work:** record a status for every selected source before attempting to stage it,
  preserve the per-source error, distinguish a source failure from a whole-candidate validation
  failure, and make the existing test assert the source id.

### G-08 Snapshot history, identity and validation are inconsistent

- **Requirement:** revision 4 §3, §4 and §5; `rebuild-validate`, `storage` and `cli` sub-run
  acceptance.
- **Current:**
  - `list_snapshots` looks only for `manifest.json` (`manifest.py:851-921`), while refresh
    snapshots contain `refresh_manifest.json` and `import_manifest.json`; consequently
    `snapshot_count` is 0 and `topomarket validate` has no history to check.
  - `validate_data_directory` (`report.py:651-751`) validates only the active snapshot directory,
    not the other entries under `snapshots/`.
  - The snapshot directory name and `refresh_manifest.json` use the normalized-content digest,
    but `import_manifest.json["snapshot_id"]` is a different `compute_snapshot_id` value.
  - `_show_report` (`cli.py:380-413`) resolves the active snapshot before reading the pointer, so
    `report --profile ...` without `--data-dir` reports `active_snapshot_id: null`; `report` also
    does not expose revision counts or added/removed rows.
- **Reproducer:**

  ```bash
  PYTHONPATH=src:tests python - <<'PY'
  from pathlib import Path
  import json, tempfile
  from topomarket.data.manifest import list_snapshots
  from topomarket.data.refresh import refresh_sources
  from topomarket.report import build_data_report
  from test_refresh import _baseline, _fetcher
  root = Path(tempfile.mkdtemp()) / "data"
  _baseline(root)
  report = refresh_sources(root, fetcher=_fetcher())
  snap = root / "snapshots" / report.new_snapshot_id
  print("history:", [item.snapshot_id for item in list_snapshots(root)])
  print("snapshot_count:", build_data_report(root)["snapshot_count"])
  print("refresh id:", json.loads((snap / "refresh_manifest.json").read_text())["snapshot_id"])
  print("import id :", json.loads((snap / "import_manifest.json").read_text())["snapshot_id"])
  PY
  # history: []
  # snapshot_count: 0
  # refresh id and import id differ
  ```

- **Remaining work:** adopt one snapshot manifest/history convention that existing readers can
  discover, validate every snapshot in history (manifests and referenced normalized tables), make
  the two snapshot id fields consistent, and fix report/status to expose the active id and
  revision/row deltas.

### G-09 `added_rows` / `removed_rows` are not deltas

- **Requirement:** revision 4 §4; `reconcile` and `rebuild-validate` sub-run acceptance.
- **Current:** `added_rows=sum(normalized_row_counts.values())` (total normalized rows) and
  `removed_rows=0` always (`refresh.py:989-998`). `refresh_manifest.json` stores
  `normalized_row_counts`, not added/removed counts.
- **Reproducer:**

  ```bash
  PYTHONPATH=src:tests python - <<'PY'
  from pathlib import Path
  import tempfile
  from topomarket.data.refresh import refresh_sources
  from test_refresh import _baseline, _fetcher
  root = Path(tempfile.mkdtemp()) / "data"
  _baseline(root)
  report = refresh_sources(root, fetcher=_fetcher())
  print("added:", report.added_rows, "removed:", report.removed_rows)
  # added: 14 removed: 0  (14 is the total normalized row count, not a delta)
  PY
  ```

- **Remaining work:** compute row-level additions/removals against the previous snapshot and
  persist them in the refresh manifest; expose them through status/report.

### G-10 Clean-rebuild proof and the Step 6 label requirement are missing

- **Requirement:** revision 4 §4 first bullet; `rebuild-validate` and `orchestrate` sub-run
  acceptance.
- **Current:** `test_revised_close_and_shorter_export_retain_history` checks
  `_normalized_digest(snapshot) == report.new_snapshot_id` (`tests/test_refresh.py:251-254`). That
  proves the published directory agrees with the id that was derived from the same candidate
  directory, not that a fresh rebuild from the staged inputs and retained history produces the
  same tables. `refresh.py`'s module docstring also does not state that Step 6 must rebuild labels
  for the 20 sessions before a revised close.
- **Remaining work:** add an independent rebuild test that starts from the staged payloads plus
  retained history, runs the merge/normalization path, and compares hashes. Add the Step 6 label
  sentence to the module docstring and `docs/REFRESH.md` (or `docs/A3_CONTRACT.md` plus the
  subsequent integration docs task).

### G-11 Required test coverage is weaker than the A3 test contract

- **Requirement:** revision 4 §Required tests 1-7; sub-run `storage`/`orchestrate-publish`
  acceptance.
- **Current gaps:**
  - **T1:** no assertion that a 304 writes no normalized tables or snapshot directory.
  - **T2:** no refresh-level test of a transient fetch failure going through the retry loop; the
    failed-source assertion in the broken-ZIP test is too weak (G-07).
  - **T4:** no unknown-schema/missing-column test; the broken-ZIP test does not name the failed
    source.
  - **T5:** no synchronized two-writer test, no assertion of a complete active manifest/history
    after a busy result, and no injected publication failure (G-08).
  - **T7:** no assertion that `received_at_utc`, attempts, backoff and timeout are recorded in the
    refresh status; see G-12.
  - Optional OFR failure test checks status but not that previous OFR rows remain in the snapshot.
- **Remaining work:** these are test additions for `tests/test_a3_update.py`,
  `tests/test_a3_recovery.py`, and `tests/test_a3_integration.py`; no behavior change is needed
  for the parts that already work.

### G-12 Retry/timeout metadata and clock injection are not fully persisted

- **Requirement:** revision 4 §1/§4 and required test 7; `fetch` and `orchestrate` sub-run
  acceptance.
- **Current:** `FetchResult` carries `attempts`, `timeout_seconds` and `fetched_at_utc`
  (`fetch.py:42-62`), but `SourceRefreshStatus` (`refresh.py:91-114`) does not persist attempts,
  backoff or timeout. `refresh_sources(clock=...)` controls `last_attempt_at` and the snapshot
  `created_at_utc`, but `_write_refresh_status` uses the real `_now_iso()` (`refresh.py:322-340`),
  so `updated_at_utc` is not deterministic under the injected clock.
- **Reproducer:**

  ```bash
  PYTHONPATH=src:tests python - <<'PY'
  from datetime import UTC, datetime
  from pathlib import Path
  import tempfile
  from topomarket.data.refresh import load_refresh_status, refresh_sources
  from test_refresh import _baseline, _fetcher
  root = Path(tempfile.mkdtemp()) / "data"
  _baseline(root)
  fixed = datetime(2000, 1, 1, tzinfo=UTC)
  report = refresh_sources(root, fetcher=_fetcher(), clock=lambda: fixed)
  print("last_attempt:", report.sources[0].last_attempt_at)       # 2000-01-01T00:00:00Z
  print("status updated:", load_refresh_status(root)["updated_at_utc"])  # real clock
  PY
  ```

- **Remaining work:** add attempts/backoff/timeout to the persisted source status (and/or the
  refresh manifest), route all timestamps through the injected clock, and test the recorded
  values.

### G-13 VIX revisions are not logged

- **Requirement:** revision 4 §3 ("compare overlapping data and log revisions"); required test 3;
  `reconcile` sub-run acceptance.
- **Current:** `_collect_revisions` iterates only `sp500_daily` and `industries_daily`
  (`refresh.py:585-622`). A changed VIX close publishes a new snapshot but produces no
  `RevisionRecord`.
- **Reproducer:**

  ```bash
  PYTHONPATH=src:tests python - <<'PY'
  from pathlib import Path
  import tempfile
  from topomarket.data.refresh import refresh_sources
  from test_refresh import _baseline, _fetcher, _bodies
  root = Path(tempfile.mkdtemp()) / "data"
  _baseline(root)
  refresh_sources(root, fetcher=_fetcher())
  bodies = _bodies()
  bodies["cboe_vix"] = bodies["cboe_vix"].replace(
      b"12/10/2018,18,20,17,23", b"12/10/2018,18,20,17,99")
  report = refresh_sources(root, fetcher=_fetcher(bodies))
  print("published:", report.published, "revisions:", report.revisions)
  # published: True revisions: ()
  PY
  ```

- **Remaining work:** compare previous and candidate VIX observations (and any other refreshed
  overlapping source) and add `RevisionRecord`s with the source id and snapshot id.

## 5. Suggested task split for the remaining work

This is guidance only; the audit does not implement any of it.

| Next task | Gaps |
| --- | --- |
| `a3-update` (update path) | G-01 (after product decision), G-02, G-03, G-05, G-06, G-09, G-10 (test/doc), G-12 (metadata), G-13 |
| `a3-recovery` (failure/recovery) | G-04, G-07, G-08 (history/atomic publication), G-11 (fault-injection/concurrency), G-12 (clock/status) |
| `a3-integration` (interfaces/docs) | G-08 (report/validate), G-02 (CLI freshness), G-10 (docs), G-11 (exit-code/integration tests), README/docs accuracy |

## 6. Audit method and limitations

- Runtime behavior was **not** changed; this audit adds only this document.
- The spec was read from the project requirement record (revision 4) plus the Step 3a/3b
  contracts (revisions 5 and 6) and the Step 3 sub-run task metadata. Step 4 revision 7 was
  ignored except to confirm it is out of scope.
- Public tests and quality gates were run on the current checkout; the baseline is recorded in
  §2. The private acceptance suite was skipped because `TOPOMARKET_SEED_DIR` is not set, as
  designed for public CI.
- The gap reproducers in §4 were executed against the current implementation and their quoted
  outputs match the current behavior. They use temporary directories and synthetic fixture
  helpers only; no network, private data, credentials, or snapshots were created in the
  repository.
- Two wording points required interpretation (default source set and "keep original bytes"). They
  are recorded in §1.4; if the project owner intends a different interpretation, only the affected
  gap entries need re-scoping. The audit found no blocker that would justify inventing A3
  requirements or starting dependent implementation.
