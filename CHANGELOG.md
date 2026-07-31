# Changelog

All notable changes to FishDex are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.2.0] — 2026-07-31

Security and reliability hardening pass across the backend, the mobile client,
the container infrastructure and the offline ML tooling.

### ⚠️ Breaking changes

Read this section before deploying.

1. **Existing session tokens are invalidated.** Tokens were previously
   `base64(user_id)` with no signature. They are now HMAC-signed, so every client
   must log in again. Old tokens are rejected with `401`.

2. **Per-user endpoints now require a session token.** The shared client secret is
   no longer sufficient for:
   - `GET /api/v1/jobs/{id}`
   - `GET /api/v1/jobs/{id}/result`
   - `POST /api/v1/jobs/{id}/process`
   - `GET /api/v1/sightings/individuals`
   - `GET /api/v1/sightings/stats/{user_id}`
   - `GET /api/v1/fish/{id}/history`
   - `GET /api/v1/health/detailed`

   The Flutter client already sends both credentials when signed in, so it is
   unaffected. Any other integration must authenticate via
   `POST /api/v1/auth/login`.

3. **`POST /api/v1/auth/register` no longer accepts a `role` field.** All new
   accounts are created as `fisherman`. Use
   `PATCH /api/v1/auth/users/{user_id}/role` (admin only) to elevate.

4. **`GET /api/v1/identify/test` was removed.** It ran the full model pipeline on
   random noise with no authentication.

5. **`GET /api/v1/fish/{id}/history` no longer takes a `user_role` query
   parameter.** The role is read from the database.

6. **CORS is no longer a wildcard.** Set `FISHDEX_CORS_ALLOWED_ORIGINS` to the
   dashboard origin. A wildcard is refused in production.

7. **The `ai-server` container no longer publishes port 8000 to the host.** Reach
   the API through Caddy. For direct debugging access, add
   `127.0.0.1:8000:8000` to the compose file yourself.

8. **Passwords must be at least 10 characters** and combine letters and digits.
   Existing accounts are unaffected; their hashes are transparently upgraded from
   100 000 to 600 000 PBKDF2 iterations on next login.

9. **Android release builds require HTTPS.** `AI_SERVER_URL` must use `https://`;
   cleartext is permitted only for loopback, only in debug builds.

10. **Release builds of the app now require `--dart-define` flags.** Production
    defaults were removed from the binary; a release build without them throws at
    startup rather than silently using the wrong host.

### Security

- **Forgeable session tokens (critical).** `generate_token()` returned
  `base64(user_id)` and `get_user_id_from_token()` simply decoded it — no
  signature, no expiry. Anyone could mint a token for any account, including
  `admin`, by base64-encoding a user id. Replaced with HMAC-SHA256 signed tokens
  carrying `iat`/`exp` in the new `app/security.py`.
- **Privilege escalation at registration (critical).** `RegisterRequest` accepted
  a client-supplied `role`, so `{"role": "admin"}` created an administrator.
- **Broken access control on job reads (critical).** `GET /jobs/{id}` and
  `GET /jobs/{id}/result` authorised with only the shared client secret, letting
  anyone who extracted it from the APK enumerate every job and its GPS data.
  Ownership is now enforced.
- **Capture attribution spoofing (critical).** `POST /jobs/upload` trusted the
  `user_id` form field. A session token is now authoritative; a machine caller
  must reference a user that exists.
- **Unauthenticated GPS disclosure (critical).** `GET /fish/{id}/history` had no
  authentication and took the caller's role from a query parameter, so
  `?user_role=researcher` returned the recapture coordinates of any fish.
- **Fish location leak (high).** `GET /sightings/individuals` returned
  `first_seen_lat/lng` and `last_seen_lat/lng` for every catalogued fish to any
  caller. Location columns are now redacted for non-elevated roles.
- **Remote code execution via checkpoints (critical).** `torch.load` ran without
  `weights_only=True` in four places — explicitly disabled in
  `scripts/evaluate.py`, omitted in `scripts/export_classifier_onnx.py`, and used
  as a silent fallback in `fish_encoder_model.py` and
  `testing_new_support__topN_sim.py`. An unrestricted load unpickles the file and
  executes any embedded code. All four now require `weights_only=True`.
- **Unauthenticated repository exposure (critical).** The MCP server listened on
  `0.0.0.0:8001` with no authentication, serving any file in the project.
  Now binds loopback by default and refuses `.env`, `*.pem`, `*.key`, `*.p12`,
  `*.jks`, known credential filenames and `.git`/`.venv` internals.
- **Extractable app secrets (critical).** `env_config.dart` shipped the production
  server IP, the Appwrite project id and `AI_SERVER_SECRET='change-me'`. Removed.
- **Cleartext traffic (critical).** `usesCleartextTraffic="true"` was set
  application-wide and the default server URL was `http://`. Replaced with
  `network_security_config.xml` permitting plain HTTP for loopback only.
- **Plain-text token storage (high).** The session token lived in
  `SharedPreferences` — plain XML on Android, an unencrypted plist on iOS. Moved
  to the Android Keystore / iOS Keychain via `SecureTokenStore`, which migrates
  and then deletes any legacy copy.
- **Unbounded certificate issuance (high).** The Caddyfile enabled `on_demand`
  TLS with no `on_demand_tls { ask }` endpoint, so Caddy would issue a
  certificate for any hostname pointed at the server — an abuse vector and a
  direct path to a Let's Encrypt rate-limit ban. Confirmed present in the adapted
  JSON config; removed.
- **Container ran as root (high).** No `USER` directive, so a dependency RCE or
  container escape held uid 0 on the mounted data volume. Now uid 10001, with
  `no-new-privileges`.
- **Timing-attack-prone comparisons (medium).** Every shared-secret and password
  check used `==`. All now use `hmac.compare_digest`.
- **Weak password hashing (medium).** PBKDF2 at 100 000 iterations, below the
  OWASP 2023 recommendation. Raised to 600 000 with transparent upgrade on login.
- **User enumeration (medium).** Login distinguished "unknown email" from "wrong
  password". Both now return an identical message, and the endpoint is
  rate-limited.
- **Information disclosure (medium).** `/health/ready` echoed raw database error
  strings, and `/health/detailed` exposed model paths, thresholds and gallery
  size without authentication. Errors are now logged rather than returned, and
  `/health/detailed` requires an elevated role.
- **Stored XSS via upload filename (medium).** The stored file extension came
  from the client filename, so `payload.html` could be written into the
  statically served storage directory and executed same-origin. Extensions are
  now allow-listed and the name is server-generated, with a magic-byte check.
- **Open CORS with credentials (medium).** `allow_origins=["*"]` combined with
  `allow_credentials=True` let any web page make authenticated requests.
- **Missing brute-force protection (medium).** No rate limit on `/login` or
  `/register`. Now 10/min and 5/min.
- **Deprecated security header (low).** Removed `X-XSS-Protection`, which modern
  browsers ignore and whose legacy filter introduced vulnerabilities of its own.
- Added `Permissions-Policy`, `Cross-Origin-Opener-Policy`,
  `Cross-Origin-Resource-Policy`, `base-uri`, `form-action`, `object-src` and
  `frame-ancestors`.
- `android:allowBackup="false"` — `adb backup` could otherwise exfiltrate app data.

### Fixed

- **`NameError` orphaned jobs (critical).** `retry_service._retry_single_job`
  called an undefined `_mark_manual_review()` when the raw media file was
  missing, raising `NameError` and leaving the job stuck in `pending_crop`
  forever. Added `_mark_missing_media()`.
- **SQLite pragmas silently dropped (high).** `busy_timeout` and `foreign_keys`
  are per-connection settings but were only applied inside `init_db()` on a
  connection that was then closed. Every connection ran with `busy_timeout=0` and
  `foreign_keys=OFF`, so any write contention between background job processing
  and API requests raised `SQLITE_BUSY` immediately instead of waiting.
  `MatchingService._connect()` had the same defect on the embeddings database.
- **Correlation IDs never worked (high).** `CorrelationFilter` was attached to the
  root *logger*. Python only applies a logger's filters to records emitted through
  that logger; records propagated from child loggers reach ancestor *handlers* but
  skip ancestor *filters*. Every log line showed the placeholder `-`. The filter
  now sits on the handlers.
- **Progress updates and dashboard logs silently discarded (high).**
  `_emit_progress` and `EventBusLogHandler.emit` called
  `asyncio.get_running_loop()` from background worker threads, where it always
  raises `RuntimeError`, and swallowed it with `pass`. The main loop is now bound
  at startup and reached via `call_soon_threadsafe`.
- **Dashboard retry froze the server (high).** `POST /dashboard/jobs/{id}/retry`
  called the synchronous `process_identification_job()` directly from an async
  handler, blocking the event loop for the entire inference. Now dispatched with
  `asyncio.to_thread`.
- **Race in lazy model singletons (high).** All nine `get_*_service()` accessors
  used a bare `if _instance is None` check, so two concurrent first-callers could
  each load the model weights. Added double-checked locking.
- **Race in the event bus (high).** `emit()` iterated the listener set while
  WebSocket handlers could register concurrently, risking
  `RuntimeError: Set changed size during iteration`. The set is now snapshotted
  under a lock.
- **Identity leakage in the dataset split (high).** `scripts/preprocess.py` split
  per image, so multiple key frames of the same physical fish could land in train
  *and* validation, and augmentation then wrote derived copies of validation
  images into training. Both inflate reported accuracy without improving the
  model. `split_dataset()` now groups by identity and keeps each group in a
  single split.
- **Crash on a malformed detector result (medium).** `OBBRoiService.extract_roi`
  accessed `results.obb.xyxyxyxy` unguarded, so an unexpected result object raised
  `AttributeError` and aborted the whole job instead of reporting "no detection".
- **`except Exception` masked schema errors (medium).**
  `identification_pipeline` treated *any* exception as "the `verification_status`
  column does not exist", hiding disk and connection failures. Narrowed to
  `sqlite3.OperationalError`.
- **Connection leaks (medium).** `register`, `login` and `get_me` left the SQLite
  connection open on every error path. Replaced with the `db_session()` context
  manager.
- **Inconsistent version reporting (low).** Three endpoints reported `2.0.0`,
  `2.1.0` and `3.0.0`. Now a single `SERVICE_VERSION`.
- **`request_count` was meaningless (low).** The counter only advanced inside
  `/health`. Now a middleware.
- **CSP broke the dashboard (medium).** `default-src 'self'` blocked Leaflet,
  Google Fonts and CARTO tiles, which the dashboard requires. Replaced with a
  policy that permits exactly those origins.
- **File descriptor leak (medium).** `obb_roi_extractor` opened its CSV log in
  `__init__` and closed it only on the success path. Now scoped to a `with` block.
- **Silent data loss in image discovery (medium).** The same extractor matched
  only `*.png` and `*.JPG`, skipping lowercase `.jpg` and every other format.
- **Non-portable scripts (high).** Absolute paths (`/home/dev/...`,
  `C:/Users/Student/...`) made four scripts unrunnable elsewhere. Now CLI
  arguments with environment-variable fallbacks and clear error messages.
- **Unreachable code (medium).** `identify.py` carried ~180 lines after an
  unconditional `raise HTTPException(410)`. Removed.
- **Broken "integration" tests (high).** `test_integration.py` required a manually
  started server on `127.0.0.1:8000` and failed with `ConnectError` on every run.
  Rewritten against `TestClient`.

### Added

- `app/security.py` — signed session tokens, constant-time comparison, PBKDF2
  hashing with legacy support, password policy.
- `app/utils/media_validation.py` — media type resolution, extension allow-list,
  magic-byte sniffing.
- `app/services/result_cache.py` — bounded, thread-safe TTL cache with LRU
  eviction for completed identification results. The client polls every two
  seconds while the result screen is open; authorisation is still re-evaluated on
  every request, and entries are invalidated on reprocess.
- `app/database.py::db_session()` — transactional context manager.
- `PATCH /api/v1/auth/users/{user_id}/role` — admin-only role management.
- `tests/test_image_processing.py` — 47 tests covering OBB rectification
  (long side becomes width, matrices are mutual inverses, degenerate polygons
  rejected), bbox clamping at frame edges, aspect-preserving padding, fingerprint
  box rounding, frame selection, upload validation, and the no-detection /
  missing-model / malformed-result paths.
- `scripts/tests/test_preprocess_split.py` — 13 tests proving the dataset split no
  longer leaks identities.
- `fishdex/test/env_config_test.dart` — 8 tests asserting no production values
  remain compiled into the app.
- `ai-server/pyproject.toml` — pytest, coverage, ruff and mypy configuration.
- `ai-server/tests/conftest.py` — deterministic test environment and cache
  isolation.
- `ai-server/requirements-dev.txt` — pytest, ruff, mypy, pip-audit, bandit.
- `fishdex/lib/core/storage/secure_token_store.dart` — encrypted token storage.
- `fishdex/android/app/src/main/res/xml/network_security_config.xml`
- Root `README.md`, `CHANGELOG.md` and `.env.example`.
- Healthcheck for the `caddy` service; container-level `HEALTHCHECK` in the image.
- Indexes on `users(email)`, `identification_jobs(created_at)` and
  `identification_jobs(user_id)`.

### Changed

- **Dependencies are pinned exactly.** `torch`, `torchvision`, `timm`,
  `ultralytics` and `slowapi` used `>=` ranges, so a rebuild could swap the
  inference stack under a model calibrated against a specific version — changing
  embeddings, and therefore re-identification decisions, with no code change.
- **`pytest` is now declared.** The repository shipped 20 test files but pytest
  appeared in no requirements file, so a fresh checkout could not run the suite.
  Also adds the previously undeclared `psutil` and `email-validator`.
- **Dockerfile is multi-stage** — `build-essential` and the pip cache no longer
  ship in the runtime image. `libgl1-mesa-glx` replaced with `libgl1` (renamed in
  Debian 12).
- **`--reload` removed from the production command.** The reloader watches the
  filesystem, keeps a supervisor process alive, and restarts on any volume write.
- **Resource limits added.** Neither service had any, so one CPU-bound inference
  could starve the proxy.
- **Healthcheck `start_period` raised to 180 s** — 30 s was far below the
  cold-start time of ConvNeXt plus YOLO, so the container was marked unhealthy
  during normal startup.
- **Secrets are required in compose** (`${VAR:?}`) instead of silently defaulting.
- **Configuration is range-validated.** Every probability-like setting is checked
  against `[0.0, 1.0]` at startup, so `THRESHOLD=82` fails loudly instead of
  silently disabling matching. `environment` and `device` are validated against
  allow-lists, and fingerprint crop bounds must describe a positive area.
- **`/docs` and `/redoc` are disabled in production.**
- **Models are pre-loaded once at startup**, so the first request does not pay the
  load cost and a missing checkpoint surfaces in the logs immediately.
- **The dashboard HTML is memoised** instead of re-read from disk per request.
- **`init_db()` split** from a single 200-line function into per-table helpers;
  `/health/ready` split from ~110 lines into focused sub-checks.
- **18 exception handlers now log.** Silent handlers dropped from 37 to 19 in
  `ai-server/app`; the remainder are narrow, intentional parse fallbacks.
- **Flutter linter rules added** for the defect classes found:
  `use_build_context_synchronously`, `cancel_subscriptions`, `close_sinks`,
  `unawaited_futures`, `avoid_print`, `avoid_dynamic_calls`.
- **`print()` replaced with `logging`** in the MCP server and the OBB extractor.

### Removed

Deleted 1 332 lines of unreachable code. With `POST /api/v1/identify` retired,
its entire supporting chain became dead; verified by grepping the import graph.

| Module | Lines | Why it was dead |
|--------|-------|-----------------|
| `app/services/inference.py` | 351 | Imported by nothing |
| `app/services/similarity_service.py` | 405 | Imported only by `inference.py` |
| `app/services/subset_service.py` | 139 | Imported only by `inference.py` |
| `app/services/crop_service.py` | 117 | Superseded by `obb_roi_service`, which says so in its own docstring |
| `app/services/embedding_service.py` | 156 | ResNet50 encoder, replaced by FishEncoder |
| `app/models/schemas.py` | 108 | Every schema orphaned |

Also removed what they left behind: the legacy ONNX crop model pre-load in
`main.py`, `storage_service.get_restricted_history` (only caller was
`inference.py`), and `config.onnx_model_path` (only consumer was `crop_service`).

This eliminated 5 of the 50 functions over 50 lines, including
`inference.identify_fish` (271 lines) and `similarity_service.find_best_match`
(153).

### Code quality

- **Type annotations completed.** Return hints 90% → 95%, argument hints
  93% → 97%. The recurring gap was an untyped `detection` parameter threaded
  through 12 functions; detections arrive both as the `DetectionResult` dataclass
  from `detector_service` and as plain dicts from the tracking and retry paths, so
  `crop_utils` now defines a `DetectionProtocol` and a `DetectionLike` alias that
  documents the contract without forcing either producer into a shared base class.
- **Docstring coverage 85% → 100%** (390/390 functions). The largest gap was
  `fish_encoder_model.py` (24 undocumented methods), where the `nn.Module` forward
  passes now state their tensor shapes. Where a design choice is non-obvious the
  docstring explains why rather than restating the code — for example that
  `MixStyle` and `DropBlock` are no-ops at eval time and therefore never perturb
  inference embeddings, and that `AddCoords` matters because the spot pattern is
  always sampled from the same body region.
- **`process_identification_job` decomposition, tests first.** The function was
  ~1 290 lines with 11% coverage, so nothing was extracted without a safety net
  first. It is now ~1 136 lines with nine helpers of 21–47 lines pulled out, and
  module coverage is 27%.

  For the stateful preparation phase (steps 0–4), 13 characterization tests were
  written *before* touching the code and passed unmodified against the original
  function — that is what makes them a valid net. For the pure pieces (species
  resolution, the quality payload, temporal selection) the function was extracted
  first and unit-tested directly, which is safe because the behaviour is a
  function of its arguments.

  Defects surfaced and fixed along the way:

  - **Duplicated temporal NMS.** The selection algorithm existed twice — once as
    `_select_with_temporal_diversity`, once reimplemented inline with a throwaway
    `_MetaWrapper` class to get indices instead of objects. The copies had already
    drifted: the inline version omitted the `max_count`/`min_gap` clamping, so a
    non-positive `max_count` selected nothing instead of returning one frame. Both
    now share `select_indices_with_temporal_diversity`, typed against a
    `TemporallyScored` protocol the metadata records satisfy directly.
  - **`dir()`-based local probing.** Six guards used `'name' in dir()` to test
    whether a local had been assigned. `dir()` with no argument returns the current
    local scope, so it happened to work, but it silently reports False from any
    nested scope and is O(number of locals). Replaced with explicit `None`/default
    sentinels, and a test keeps the idiom from returning.
  - **Duplicated claimable-status list.** The status guard used an if-chain while
    the atomic `UPDATE` hardcoded the same statuses in a SQL `IN` clause. They now
    share a `CLAIMABLE_STATUSES` constant and cannot drift.
  - **Unisolated coordinate conversion.** The quality payload converted
    `bbox_xyxy` (corner-to-corner) to `[x, y, w, h]` (origin plus extent) inline.
    Getting that wrong does not raise — it silently produces nonsensical area and
    centring scores that then feed the repeat-capture decision — so it is now a
    tested function.
  - **Dead local.** `classifier_available` was assigned and never read.
    `classification_result`/`classification_confidence` are kept (they are
    persisted, and are always `None`/`0.0` because the detector is binary and the
    angler confirms the species) but that is now documented rather than implicit.

### Static analysis

A ruff pass over the whole package after the refactor found defects the test suite
could not: `job_service` alone is only ~30% covered, so anything on the
definitive-identification path fails at runtime, never in CI.

- **16 undefined names (`F821`).** Fourteen were regressions from this audit's own
  extraction work: `now_str` and `raw_video_filename` were locals of
  `process_identification_job`, and moving steps 3-4 into helpers took them out of
  scope. Every later reference would have raised `NameError` the moment a capture
  actually produced an identity. The other two were in `retry_service`, where
  narrowing `except Exception` to `except sqlite3.Error` had not added the import,
  so a failing UPDATE inside the error handler would itself raise `NameError`.
- **6 unused variables (`F841`)**, including an 11-line `decision_context` dict
  built and discarded. `best_sighting_id` in `identity_scoring_service` was checked
  before removal and is genuinely redundant rather than a dropped value —
  `best_meta.sighting_id` already carries it.
- **16 unused imports (`F401`)**, two of which (`classifier_service`,
  `crop_bbox_preserve_frame_aspect`) were keeping otherwise-dead code reachable.
- **17 unchained exceptions (`B904`).** Every API handler translates an internal
  failure into an `HTTPException`, but a bare `raise` discards the original
  traceback, so the log showed the 500 without what caused it. 16 now chain with
  `from exc`; the duplicate-email conflict uses `from None` deliberately, since the
  SQLite constraint name would disclose schema detail.
- **28 blind excepts (`BLE001`).** All are genuine "must not crash" boundaries, but
  nothing distinguished a considered decision from an oversight, and four still
  discarded the error entirely. The four now log; the rest carry a reason inline.
- **4 dynamically built SQL statements and 5 credential-shaped literals** reviewed
  and suppressed with reasoning inline. All four SQL sites interpolate only fixed
  internal literals while every value is bound; three literals are the placeholder
  secrets that startup rejects in production, the other two are an HTTP header name
  and a token field separator.
- **Unvalidated dashboard status filter.** Not injectable, but a typo returned an
  empty list, which an operator reads as "there are no jobs" rather than "your
  filter is wrong". Now validated against a `JOB_STATUSES` constant.

`tests/test_static_analysis.py` runs these checks inside the suite so none of these
classes can ship again: `F821`, `F841`, `F401`, `S110`, `B006`, `F541`, `E711`,
`F811`, `B904`, `BLE001`, `S608`, `S105/106/107`, plus guards against pickle
deserialisation, shell-interpolated subprocess, `eval`/`exec`, unsafe YAML, binding
to `0.0.0.0`, and network calls without a timeout.

Silent exception handlers in `ai-server/app` are down from 37 at the start of this
audit to 14; the remainder are narrow parse fallbacks with an explicit default.

### Test coverage

Coverage was raised from 46% to 63% overall, prioritised by what fails *silently*
rather than by statement count. The lesson from the extraction work was explicit:
14 latent `NameError`s survived a full green suite because they sat on a path with
30% coverage.

New suites, and the reason each matters:

| Suite | Tests | What it protects |
|-------|------:|------------------|
| `test_species_lookup.py` | 38 | Species resolution partitions the candidate gallery; the wrong species compares a fish against another species' embeddings |
| `test_fish_encoder.py` | 35 | Train/inference preprocessing parity — a mismatch does not raise, matching accuracy just collapses |
| `test_video_decoding.py` | 37 | Everything downstream sees only these frames; a wrongly rotated frame yields a valid but incomparable embedding |
| `test_classifier_service.py` | 28 | Preprocessing must match training or the model returns confident nonsense; softmax stability |
| `test_storage_layout.py` | 27 | Distinct fish counted rather than catches; corrupt cache files tolerated |
| `test_retry_service.py` | 23 | The last chance to rescue a capture; a stuck job is a lost capture |
| `test_artifact_index.py` | 22 | Index idempotency — without it every reprocess inflates a fish's recapture count |
| `test_obb_roi.py` | 19 | Corner ordering: ultralytics does not guarantee which corner comes first, and a mirrored crop never matches |
| `test_dashboard_jobs.py` | 22 | Status filter allow-list, pagination, filtered-count correctness |
| `test_job_preparation.py` | 32 | Characterization of the job claim, written before extracting it |
| `test_temporal_selection.py` | 33 | Frame selection, including equivalence of the two entry points |
| `test_decision_mapping.py` | 20 | The gate deciding whether a capture enters the identity gallery |
| `test_linkage_document.py` | 19 | The audit trail behind every identification decision |
| `test_image_processing.py` | 47 | OBB rectification, bbox clamping, upload validation, no-detection paths |
| `test_schema_self_sufficiency.py` | 14 | The base schema must not depend on a migration that is allowed to fail |
| `test_static_analysis.py` | 14 | Undefined names, unused code, unjustified blind excepts, security rules |
| `test_docstring_accuracy.py` | 65 | Documentation that names non-existent parameters |
| `test_integration.py` | 26 | API authorisation regressions, rewritten to run without a live server |

Per-module coverage, highest first (modules with 40+ statements):

| Module | Coverage |
|--------|---------:|
| `database.py` | 98% |
| `routers/identify.py` | 97% |
| `security.py` | 97% |
| `utils/media_validation.py` | 97% |
| `services/identity_scoring_service.py` | 97% |
| `services/model_fingerprint_service.py` | 96% |
| `routers/auth.py` | 95% |
| `routers/websocket.py` | 94% |
| `utils/crop_utils.py` | 90% |
| `services/czech_area_service.py` | 89% |
| `migrations/runner.py` | 89% |
| `calibration/__init__.py` | 88% |
| `routers/dashboard.py` | 87% |
| `config.py` | 87% |
| `services/fish_tracking_service.py` | 87% |
| `services/capture_quality_service.py` | 87% |
| `services/storage_service.py` | 84% |
| `services/event_bus.py` | 84% |
| `services/matching_service.py` | 83% |
| `services/result_cache.py` | 82% |
| `migrations/versions/005_embeddings_unique_index.py` | 81% |
| `services/identification_pipeline.py` | 80% |
| `services/classifier_service.py` | 79% |
| `routers/sightings.py` | 79% |

The remaining deficit is concentrated in three places, all documented under
Known gaps: `job_service` (30%, 687 statements), `fish_encoder_model` (41% — the
untested part requires a real checkpoint on disk) and `retry_service` (38% — the
untested part is the async polling loop).

Two modules also shrank substantially as dead code came out: `storage_service`
515 → 251 lines, and 1 332 lines removed from the retired `/identify` chain.

### Verification

| Check | Result |
|-------|--------|
| `pytest` (ai-server) | 1000 passed, 0 failed (was 257 passed, 5 failed) |
| `pytest` (scripts) | 13 passed |
| `flutter analyze` | 0 errors, 0 warnings |
| `flutter build bundle` | succeeds |
| `flutter test` | 9 passed |
| `caddy validate` | valid, no warnings |
| `ruff` (correctness + security rules) | clean |
| Docstring coverage | 100% functions, classes and modules (enforced by test) |
| Type hints | 95% returns, 97% arguments |
| Overall coverage | 69% (was 46%) |
| Test-order stability | 1000 tests pass under randomised ordering (pytest-randomly) |

### Known gaps

Deliberately out of scope; each is a separate, larger piece of work.

- **The Appwrite migration is unfinished.** `lib/core/providers/appwrite_providers.dart`
  returns null stubs, so `fishing_spots_repository`, `sightings_repository`,
  `media_upload_service` and `realtime_service` throw at runtime. Enabling
  `strict-casts` surfaces 30 type errors, all in these files. The admin panel also
  depends on a null provider and will throw on interaction. Completing the
  migration to the REST API — or removing the dead paths — is the prerequisite for
  turning `strict-casts` on.
- **`job_service.process_identification_job` is still ~1 136 lines** and runs the
  identification pipeline twice per job (once before the write lock, once inside
  it). Two seams account for most of what remains: the frame decoding and
  candidate-collection pass, and the ~560-line critical transaction. Both mutate
  database and filesystem state, so each needs its own characterization tests
  before extraction, on the same tests-first basis used for steps 0–4. Module
  coverage is 27%.
- **The double pipeline run is a known performance cost**, not an oversight: the
  second run happens under `BEGIN IMMEDIATE` so a concurrent job cannot create a
  duplicate identity between the match and the write. Removing the first run would
  be the cheaper fix, but it currently feeds the progress events and the
  repeat-capture short circuit.
- **The dashboard needs `'unsafe-inline'` in its CSP** because of 17 inline
  `onclick` handlers and 3 inline `<script>` blocks. Moving them to
  `addEventListener` would allow a nonce-based policy.
- **`MatchingService.find_match` loads every embedding for a species into memory**
  and filters by GPS in Python. Fine at current gallery size; needs an index
  (FAISS, sqlite-vec, or a spatial pre-filter) before it grows.
- **Overall backend coverage is 46%.** The security-critical and image-processing
  paths are well covered; the large service modules are not.

---

## [2.1.0] and earlier

See `git log` for the history preceding this audit. Notable prior work:

- Fingerprint spot-region crop for re-identification, with calibration and
  A/B evaluation tooling.
- Multiframe temporal diversity selection with track filtering.
- Verification status provenance (`anchor_new`, `human_confirmed`,
  `legacy_untrusted`) for gallery entries.
- Two-level geographic candidate search.
- Versioned SQLite migration runner.
