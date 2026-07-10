# FishDex Backend Architecture

## 1. System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FLUTTER CLIENT                               │
│  (iOS/Android - Dart)                                                │
│  - Camera capture → video recording                                  │
│  - Offline queue (SQLite)                                            │
│  - Realtime subscription for job status                              │
└──────────┬──────────────────────────────────────┬───────────────────┘
           │                                      │
           │  Appwrite SDK                        │  HTTP REST
           │  (Auth, Storage, DB, Realtime)       │  (Job trigger)
           ▼                                      ▼
┌─────────────────────────────┐    ┌─────────────────────────────────┐
│        APPWRITE CLOUD        │    │         AI SERVER (Worker)       │
│                              │    │         (Python / FastAPI)       │
│  ┌────────────────────────┐  │    │                                 │
│  │  Auth                  │  │    │  POST /api/v1/jobs/{id}/process │
│  │  - Email/password      │  │    │                                 │
│  │  - OAuth (Google)      │  │    │  Pipeline:                      │
│  │  - JWT tokens          │  │    │  1. Download video              │
│  └────────────────────────┘  │    │  2. Extract frames              │
│                              │    │  3. YOLOv8 OBB detection        │
│  ┌────────────────────────┐  │    │  4. Species classification      │
│  │  Storage               │  │    │  5. Embedding + matching        │
│  │  - capture_raw_videos  │◄─┼────┤  6. Upload results              │
│  │  - capture_frames      │  │    │  7. Update documents            │
│  │  - fish_reference_imgs │  │    │                                 │
│  │  - user_avatars        │  │    │  Models:                        │
│  │  - exports             │  │    │  - fish_detector_v1.onnx        │
│  └────────────────────────┘  │    │  - fish_classifier_v1.onnx      │
│                              │    │  - fish_embedder_v1.onnx        │
│  ┌────────────────────────┐  │    │                                 │
│  │  Database              │  │    └─────────────────────────────────┘
│  │  - 10 collections      │  │                 │
│  │  - Document perms      │  │                 │ Appwrite Server SDK
│  └────────────────────────┘  │                 │ (API Key auth)
│                              │◄────────────────┘
│  ┌────────────────────────┐  │
│  │  Realtime              │  │
│  │  - Job status updates  │  │
│  │  - Sighting feeds      │  │
│  └────────────────────────┘  │
│                              │
└──────────────────────────────┘
```

---

## 2. Job-Based Identification Flow

### Step-by-step process:

```
Flutter                          Appwrite                         AI Server
  │                                │                                │
  │ 1. Record underwater video     │                                │
  │────────────────────────────►   │                                │
  │ 2. Upload video                │                                │
  │   POST /storage/files          │                                │
  │   bucket: capture_raw_videos   │                                │
  │────────────────────────────►   │                                │
  │   ◄─── file_id ───────────    │                                │
  │                                │                                │
  │ 3. Create job document         │                                │
  │   POST /databases/.../docs     │                                │
  │   status: "uploaded"           │                                │
  │────────────────────────────►   │                                │
  │   ◄─── job_id ────────────    │                                │
  │                                │                                │
  │ 4. Trigger processing          │                                │
  │───────────────────────────────────────────────────────────────► │
  │   POST /api/v1/jobs/{job_id}/process                            │
  │   Header: X-AI-Secret: {secret}                                 │
  │                                │                                │
  │ 5. Subscribe to realtime       │                                │
  │   channel: databases...jobs.{job_id}                            │
  │────────────────────────────►   │                                │
  │                                │   6. Validate request          │
  │                                │   ◄────────────────────────────│
  │                                │      GET job doc, check status │
  │                                │   ────────────────────────────►│
  │                                │                                │
  │                                │   7. Update status=processing  │
  │                                │   ◄────────────────────────────│
  │   ◄─── realtime event ────    │                                │
  │                                │                                │
  │                                │   8. Download video from bucket│
  │                                │   ◄────────────────────────────│
  │                                │   ────────────────────────────►│
  │                                │                                │
  │                                │   9. Extract frames            │
  │                                │      - Sample N frames evenly  │
  │                                │      - Score sharpness/quality │
  │                                │      - Select best 5           │
  │                                │                                │
  │                                │   10. YOLOv8 OBB detection     │
  │                                │      - Run detector on frames  │
  │                                │      - If detection: crop OBB  │
  │                                │      - If no detection: center │
  │                                │        crop fallback           │
  │                                │                                │
  │                                │   11. Species classification   │
  │                                │      - If model available:     │
  │                                │        classify species        │
  │                                │      - If no model or low conf:│
  │                                │        status=needs_review     │
  │                                │                                │
  │                                │   12. Embedding + matching     │
  │                                │      - Generate embedding      │
  │                                │      - Search existing fish    │
  │                                │        in same area+species    │
  │                                │      - If match > threshold:   │
  │                                │        link to existing fish   │
  │                                │      - Else: create new fish   │
  │                                │        individual              │
  │                                │                                │
  │                                │   13. Upload processed frames  │
  │                                │      bucket: capture_frames    │
  │                                │   ◄────────────────────────────│
  │                                │   ────────────────────────────►│
  │                                │                                │
  │                                │   14. Create documents         │
  │                                │      - fish_sightings          │
  │                                │      - fish_individuals (or    │
  │                                │        update existing)        │
  │                                │      - media_files (registry)  │
  │                                │   ◄────────────────────────────│
  │                                │   ────────────────────────────►│
  │                                │                                │
  │                                │   15. Update user stats        │
  │                                │      - total_xp += xp_earned  │
  │                                │      - level (recalculate)     │
  │                                │      - total_sightings++       │
  │                                │      - unique_species (if new) │
  │                                │      - biggest_fish_cm         │
  │                                │      - rare_fish_count         │
  │                                │      - Check achievements      │
  │                                │   ◄────────────────────────────│
  │                                │   ────────────────────────────►│
  │                                │                                │
  │                                │   16. Update job               │
  │                                │      status: completed         │
  │                                │      result_sighting_id: ...   │
  │                                │      result_fish_id: ...       │
  │                                │      confidence: 0.87          │
  │                                │   ◄────────────────────────────│
  │   ◄─── realtime event ────    │   ────────────────────────────►│
  │                                │                                │
  │ 17. Show ResultScreen          │                                │
  │     (or CaptureFormScreen      │                                │
  │      if needs_review)          │                                │
  │                                │                                │
```

### Status Transitions

```
uploaded → processing → completed
                     → needs_review → completed (after manual review)
                     → failed
```

### XP Calculation

| Event | XP |
|-------|----|
| New sighting (common) | 10 |
| New sighting (uncommon) | 25 |
| New sighting (rare) | 50 |
| New sighting (legendary) | 100 |
| New species discovered | 50 bonus |
| New fish individual | 25 bonus |
| Re-sighting known fish | 15 |

### Level Formula

```
level = floor(sqrt(total_xp / 100))
```

---

## 3. Security

### AI Server Authentication

The AI Server uses a shared secret for request validation:

```
Header: X-AI-Secret: ${FISHDEX_AI_SECRET}
```

The AI Server validates this header on every incoming request. If missing or invalid, return `401 Unauthorized`.

### Appwrite API Key (Server-side)

The AI Server uses an Appwrite API Key with the following scopes:
- `databases.read` / `databases.write`
- `storage.read` / `storage.write`
- `users.read` / `users.write`

This key is stored as `FISHDEX_APPWRITE_API_KEY` and never exposed to clients.

### Flutter Client Authentication

- Users authenticate via Appwrite Auth (email/password or OAuth)
- Appwrite SDK handles JWT tokens automatically
- Document permissions enforce that users can only read/write their own data
- Admin role users have broader permissions via Appwrite teams

### Permission Model

| Collection | Create | Read | Update | Delete |
|------------|--------|------|--------|--------|
| users | server | owner + admins | owner + server | admins |
| identification_jobs | owner | owner + server | server | admins |
| fish_sightings | server | any authenticated | server | admins |
| fish_individuals | server | any authenticated | server | admins |
| media_files | owner + server | owner + server | server | admins |
| achievements | admins | any | admins | admins |
| user_achievements | server | owner | none | admins |
| approval_requests | owner | owner + admins | admins | admins |
| fishing_areas | admins | any | admins | admins |
| leaderboards | server | any | server | server |

---

## 4. Offline Handling

### SQLite Queue

When the device is offline, Flutter stores pending jobs in a local SQLite database:

```sql
CREATE TABLE offline_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  action TEXT NOT NULL,          -- 'create_job'
  media_path TEXT NOT NULL,      -- local file path to video
  area_code TEXT,
  area_name TEXT,
  latitude REAL,
  longitude REAL,
  species_slug TEXT,
  notes TEXT,
  created_at TEXT NOT NULL,
  sync_status TEXT DEFAULT 'pending',  -- pending/syncing/synced/failed
  retry_count INTEGER DEFAULT 0,
  last_error TEXT
);
```

### Sync Strategy

1. **Connectivity monitor** - Listen to network state changes
2. **On reconnect** - Process queue in FIFO order:
   - Upload video to Appwrite Storage
   - Create `identification_jobs` document
   - Trigger AI Server processing
   - Mark queue item as `synced`
3. **Retry logic** - Exponential backoff (1s, 2s, 4s, 8s, max 60s)
4. **Conflict resolution** - Server wins; if job already exists, skip
5. **Media cleanup** - Delete local video after successful upload confirmation

### Offline UI

- Show queue count badge
- Allow viewing pending items
- Allow deleting pending items
- Show sync progress indicator

---

## 5. Environment Configuration

All environment variables use the `FISHDEX_` prefix.

### AI Server (.env)

```bash
# .env.example for ai-server

# Appwrite Connection
FISHDEX_APPWRITE_ENDPOINT=https://cloud.appwrite.io/v1
FISHDEX_APPWRITE_PROJECT_ID=your_project_id
FISHDEX_APPWRITE_API_KEY=your_server_api_key

# AI Server Config
FISHDEX_AI_SECRET=your_shared_secret_for_flutter_to_ai
FISHDEX_AI_HOST=0.0.0.0
FISHDEX_AI_PORT=8000
FISHDEX_AI_WORKERS=2

# Model Paths
FISHDEX_MODEL_DETECTOR=models/detector/fish_detector_v1.onnx
FISHDEX_MODEL_CLASSIFIER=models/classifier/fish_classifier_v1.onnx
FISHDEX_MODEL_EMBEDDER=models/embedder/fish_embedder_v1.onnx

# Processing Config
FISHDEX_MAX_FRAMES=30
FISHDEX_BEST_FRAMES=5
FISHDEX_DETECTION_CONFIDENCE=0.5
FISHDEX_MATCH_THRESHOLD=0.75
FISHDEX_FALLBACK_CROP_RATIO=0.6

# Storage Bucket IDs
FISHDEX_BUCKET_RAW_VIDEOS=capture_raw_videos
FISHDEX_BUCKET_FRAMES=capture_frames
FISHDEX_BUCKET_REFERENCE=fish_reference_images

# Database IDs
FISHDEX_DATABASE_ID=fishdex_db
FISHDEX_COLLECTION_JOBS=identification_jobs
FISHDEX_COLLECTION_SIGHTINGS=fish_sightings
FISHDEX_COLLECTION_FISH=fish_individuals
FISHDEX_COLLECTION_MEDIA=media_files
FISHDEX_COLLECTION_USERS=users
FISHDEX_COLLECTION_ACHIEVEMENTS=achievements
FISHDEX_COLLECTION_USER_ACHIEVEMENTS=user_achievements
```

### Flutter (.env)

```bash
# .env.example for Flutter app

FISHDEX_APPWRITE_ENDPOINT=https://cloud.appwrite.io/v1
FISHDEX_APPWRITE_PROJECT_ID=your_project_id
FISHDEX_AI_SERVER_URL=https://your-ai-server.com
FISHDEX_AI_SECRET=your_shared_secret_for_flutter_to_ai
```

### Key Principles

- Never commit `.env` files to version control
- Use `.env.example` as a template (committed, no real values)
- In production, use proper secret management (Docker secrets, cloud KMS)
- The `FISHDEX_AI_SECRET` must match between Flutter and AI Server
- Appwrite API Key scope should be minimal (principle of least privilege)
