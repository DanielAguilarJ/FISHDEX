# FishDex

Individual fish identification and recapture tracking for Czech fishing waters.

FishDex answers a question a photo alone cannot: **is this the same fish that was
caught here before?** A short video of a catch is turned into a species record and
matched against a gallery of previously seen individuals using the animal's own
markings — the aquatic equivalent of face recognition.

---

## How it works

A capture goes through seven stages:

| # | Stage | What happens |
|---|-------|--------------|
| 0 | **Ingest** | Video or photo uploaded, frames extracted, sharpest frames selected |
| 1 | **Species** | Confirmed from the angler's input against the Czech catalog |
| 2 | **Localise** | YOLOv8 OBB finds the fish and its orientation; the ROI is deskewed to a horizontal rectangle |
| 3 | **Fingerprint** | Optional crop of the spot-pattern region, the most individuating area |
| 4 | **Embed** | FishEncoder (ConvNeXt-Small, 512-D) turns each ROI into a vector |
| 5 | **Retrieve** | Candidates narrowed by species and a two-level geographic search |
| 6 | **Decide** | Prototype top-N majority vote; a recapture requires both a similarity threshold and a margin over the runner-up |

The decision is deliberately conservative: **merging two different fish is worse
than missing a recapture**, because a wrong merge corrupts the gallery and every
future comparison against it. Automatic matching stays disabled until a
calibration file with a measured false-accept rate is present.

### Why an oriented bounding box

A fish photographed at an angle occupies a diagonal region. An axis-aligned box
around it is mostly water, and the pattern is sheared. The OBB gives the rotation,
so every crop reaching the encoder is normalised the same way — which is what
makes embeddings from different sessions comparable.

---

## Architecture

```
                      ┌──────────────────┐
                      │  Flutter app     │   Android / iOS
                      │  (fishdex/)      │
                      └────────┬─────────┘
                               │ HTTPS
                               │ X-FishDex-Client-Secret + Bearer <session token>
                      ┌────────▼─────────┐
                      │  Caddy           │   TLS, security headers, 55 MB body cap
                      │  (Caddyfile)     │
                      └────────┬─────────┘
                               │ HTTP (internal network only)
                      ┌────────▼─────────┐
                      │  FastAPI         │   ai-server/
                      │  ai-server       │
                      └────────┬─────────┘
                               │
        ┌──────────────┬───────┴────────┬──────────────────┐
        │              │                │                  │
┌───────▼──────┐ ┌─────▼──────┐ ┌───────▼───────┐ ┌────────▼────────┐
│ YOLOv8 OBB   │ │ FishEncoder│ │ SQLite        │ │ SQLite          │
│ detector     │ │ ReID       │ │ operational   │ │ embeddings      │
│ (.pt)        │ │ (.pt)      │ │ (jobs, users) │ │ (gallery)       │
└──────────────┘ └────────────┘ └───────────────┘ └─────────────────┘
```

### Repository layout

| Path | Contents |
|------|----------|
| `ai-server/` | FastAPI service: routers, services, migrations, tests |
| `fishdex/` | Flutter mobile client |
| `mcp-server/` | Read-only codebase server for AI agents (development tooling) |
| `scripts/` | Offline training, evaluation and dataset preparation |
| `ai-server/scripts/` | Operational tooling: threshold calibration, A/B evaluation, index rebuild |
| `OBB_ROI_detector/`, `Identifier_model_GE_S03_S07/` | Model weights (Git LFS) |
| `docs/` | Backend architecture, database schema, training and ReID pipeline notes |

### Module dependencies

```
routers/jobs ──────────► services/job_service ──► services/identification_pipeline
     │                          │                          │
     │                          │                          ├─► obb_roi_service ──► detector_service
     │                          │                          ├─► reid_embedding_service ──► fish_encoder_model
     │                          │                          ├─► identity_scoring_service
     │                          │                          └─► identity_decision_service
     │                          │
     │                          ├─► matching_service (embeddings DB)
     │                          ├─► artifact_service / storage_service
     │                          └─► event_bus ──► routers/websocket (dashboard)
     │
     ├─► services/result_cache
     └─► middleware/auth ──► security (HMAC session tokens)

routers/sightings ─────► routers/auth (get_current_user) ──► database (db_session)
routers/identify ──────► reference data (czech_areas, czech_species)
routers/dashboard ─────► job_service, system_monitor
```

The **canonical** identification path is `POST /api/v1/jobs/upload`. The older
`POST /api/v1/identify` returns `410 Gone`: it lacked calibration gating and could
contaminate the gallery.

---

## Getting started

### Requirements

- Docker and Docker Compose, **or** Python 3.11–3.12 for a bare-metal run
- Flutter 3.24+ for the mobile client
- Git LFS (model weights are LFS objects)

### 1. Configure

```sh
cp .env.example .env
```

Generate each secret separately and paste it into `.env`:

```sh
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

`FISHDEX_AI_SERVER_SECRET`, `FISHDEX_CLIENT_SECRET` and
`FISHDEX_DASHBOARD_SECRET` are all required. **The server refuses to start in
production while any of them holds a placeholder value.**

`FISHDEX_AI_SERVER_SECRET` doubles as the HMAC key for user session tokens, so
rotating it logs everyone out.

### 2. Place the model weights

```
ai-server/models/detector/obb_best.pt    # YOLOv8 OBB
ai-server/models/reid/reid_best.pt       # FishEncoder
```

Without these, `/health/ready` returns `503` and Caddy will not route traffic —
by design.

### 3. Run

```sh
docker compose --env-file .env up -d --build
docker compose logs -f ai-server
```

| URL | Purpose |
|-----|---------|
| `https://localhost:8443/` | Operator dashboard |
| `https://localhost:8443/health/live` | Liveness |
| `https://localhost:8443/health/ready` | Full pipeline readiness |
| `https://localhost:8443/docs` | OpenAPI (non-production only) |

Local development trusts Caddy's internal CA, so expect a browser warning.

### Bare metal

```sh
cd ai-server
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export FISHDEX_ENVIRONMENT=development FISHDEX_SKIP_AUTH=true
uvicorn app.main:app --reload --port 8000
```

`FISHDEX_SKIP_AUTH=true` disables all authentication and is rejected outright
when `FISHDEX_ENVIRONMENT=production`.

### 4. Build the mobile app

Configuration is compile-time; nothing is read from `.env`.

```sh
cd fishdex
flutter pub get

# Development against a local server (emulator: 10.0.2.2 is the host)
flutter run

# Release
flutter build apk --release \
  --dart-define=AI_SERVER_URL=https://ai.example.org \
  --dart-define=AI_SERVER_SECRET="$FISHDEX_CLIENT_SECRET" \
  --dart-define=APPWRITE_ENDPOINT=https://fra.cloud.appwrite.io/v1 \
  --dart-define=APPWRITE_PROJECT_ID=your-project-id \
  --dart-define=DATABASE_ID=fishdex_db
```

`AI_SERVER_URL` **must** be `https://` in release builds; the app throws at
startup otherwise. Cleartext HTTP is permitted only for loopback addresses, and
only in debug builds.

---

## Running tests

### Backend

```sh
cd ai-server
pip install -r requirements.txt -r requirements-dev.txt
pytest                                  # 787 tests
pytest --cov=app --cov-report=term      # with coverage
pytest -m "not slow"                    # skip tests that load real weights
```

### Dataset tooling

```sh
python -m pytest scripts/tests/ -v      # 13 tests
```

### Mobile app

```sh
cd fishdex
flutter analyze   # must report 0 errors and 0 warnings
flutter test
```

### Linting and security scans

```sh
cd ai-server
ruff check app tests
ruff format --check app tests
mypy app
pip-audit
bandit -r app -ll
```

---

## Security model

| Concern | Position |
|---------|----------|
| **Session tokens** | HMAC-SHA256 signed, carrying `iat`/`exp`, 7-day TTL. Cannot be forged client-side. |
| **Passwords** | PBKDF2-HMAC-SHA256, 600 000 iterations, per-user salt, constant-time verification. Legacy hashes are upgraded on next login. |
| **Roles** | Always read from the database. Never accepted from a request body, query parameter or token claim. Registration always creates a `fisherman`; elevation is admin-only. |
| **Client secret** | Identifies the *application*, not a user. Extractable from the APK, so never sufficient on its own for per-user data. |
| **Location privacy** | Precise fish GPS is restricted to `researcher` and `admin`. Fishermen see only their own captures, and historical coordinates are redacted from results. |
| **Uploads** | Server-generated filenames, allow-listed extensions, magic-byte check, size cap. A client filename never influences the stored path. |
| **Checkpoints** | `torch.load(weights_only=True)` everywhere. An unrestricted load executes code embedded in a `.pt`. |
| **Transport** | TLS terminated at Caddy with HSTS, CSP, Permissions-Policy and COOP/CORP. The API port is not published to the host. |
| **Containers** | Non-root (uid 10001), `no-new-privileges`, read-only model mounts, CPU and memory limits. |

### Roles

| Role | Own captures | Others' captures | Fish GPS history | Force reprocess | Grant roles |
|------|--------------|------------------|------------------|-----------------|-------------|
| `fisherman` | ✅ | ❌ | ❌ | ❌ | ❌ |
| `researcher` | ✅ | ✅ | ✅ | ✅ | ❌ |
| `admin` | ✅ | ✅ | ✅ | ✅ | ✅ |

### Reporting a vulnerability

Open a private security advisory on the repository rather than a public issue.

---

## Operations

### Calibrate the matching threshold

Automatic matching stays off until a validated calibration exists. This is
intentional: an uncalibrated threshold has an unknown false-accept rate, and a
false accept permanently merges two fish.

```sh
cd ai-server
python scripts/calibrate_threshold.py --help
python scripts/evaluate_ab.py --help     # compare a candidate against the active config
```

### Rebuild the embedding gallery

Required after changing the model, the image size, or the fingerprint crop
bounds — embeddings produced under different settings are not comparable.

```sh
cd ai-server
python -m app.commands rebuild_embeddings
python -m app.commands audit_embeddings
```

### Reset an environment

`scripts/reset_production_environment.py` deletes all operational data. It
requires `--confirm RESET` and takes a timestamped backup first.
`scripts/reset_contaminated_identity.py` is dry-run by default and needs
`--execute` to write anything.

---

## Documentation

| Document | Contents |
|----------|----------|
| [`docs/backend_architecture.md`](docs/backend_architecture.md) | Service boundaries and request flow |
| [`docs/database_schema_v2.md`](docs/database_schema_v2.md) | Tables, indexes, migrations |
| [`docs/reid_pipeline.md`](docs/reid_pipeline.md) | Re-identification design |
| [`docs/model_training_yolov8_obb.md`](docs/model_training_yolov8_obb.md) | Detector training |
| [`docs/estructura_app.md`](docs/estructura_app.md) | Flutter app structure |
| [`docs/server_dashboard.md`](docs/server_dashboard.md) | Operator dashboard |
| [`CHANGELOG.md`](CHANGELOG.md) | Release history |

---

## License

See the repository owner for licensing terms.
