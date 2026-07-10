# FishDex Database Schema v2

## Naming Conventions

- All field names use `snake_case`
- All timestamps are ISO 8601 strings (e.g. `2025-01-15T14:30:00.000Z`)
- Coordinates stored as `double` (latitude/longitude)
- File references store `file_id` (Appwrite Storage file ID), never URLs
- Document IDs use Appwrite `$id` unless otherwise noted
- Arrays stored as JSON arrays

---

## Collections

### 1. users

Mirrors Appwrite Auth user. Created on first login.

| Field | Type | Description |
|-------|------|-------------|
| user_id | string (PK) | Same as Appwrite Auth `$id` |
| username | string | Unique display name |
| email | string | From Auth |
| role | enum | `fisherman` / `researcher` / `admin` |
| approval_status | enum | `pending` / `approved` / `rejected` (researchers need approval) |
| total_xp | integer | Cumulative experience points |
| level | integer | Derived from total_xp |
| total_sightings | integer | Count of confirmed sightings |
| unique_species | integer | Count of distinct species seen |
| biggest_fish_cm | double | Largest fish recorded (cm) |
| rare_fish_count | integer | Number of rare fish sighted |
| legendary_fish_count | integer | Number of legendary fish sighted |
| avatar_file_id | string | File ID in `user_avatars` bucket |
| share_location | boolean | Whether user shares GPS in leaderboards |
| institution | string | For researchers (university/org name) |
| bio | string | Short user bio |
| last_activity_at | string | ISO 8601 timestamp |
| created_at | string | ISO 8601 timestamp |
| updated_at | string | ISO 8601 timestamp |

**Indexes:**
- `user_id` (unique, primary)
- `username` (unique)
- `email` (unique)
- `role` (key)
- `total_xp` (descending, for leaderboard queries)
- `level` (key)

---

### 2. identification_jobs

Tracks the lifecycle of a single fish identification request.

| Field | Type | Description |
|-------|------|-------------|
| job_id | string (PK) | Appwrite `$id` |
| user_id | string | Reference to `users.user_id` |
| status | enum | `uploaded` / `processing` / `completed` / `needs_review` / `failed` |
| raw_video_file_id | string | File ID in `capture_raw_videos` bucket |
| area_code | string | Fishing area code (e.g. `471011`) |
| area_name | string | Human-readable area name |
| latitude | double | Capture location lat |
| longitude | double | Capture location lng |
| species_slug | string | Optional pre-selected species slug |
| notes | string | User notes about the capture |
| result_sighting_id | string | Created sighting ID (on success) |
| result_fish_id | string | Created/matched fish individual ID |
| confidence | double | AI confidence score 0.0-1.0 |
| species_common | string | Identified species common name |
| error_message | string | Error details (on failure) |
| started_at | string | ISO 8601 when processing began |
| completed_at | string | ISO 8601 when processing finished |
| created_at | string | ISO 8601 timestamp |
| updated_at | string | ISO 8601 timestamp |

**Indexes:**
- `job_id` (unique, primary)
- `user_id` (key, for listing user's jobs)
- `status` (key, for worker polling)
- `user_id + status` (composite, for user's pending jobs)
- `created_at` (descending)

---

### 3. fish_sightings

A confirmed observation of a fish. One sighting = one fish seen once.

| Field | Type | Description |
|-------|------|-------------|
| sighting_id | string (PK) | Appwrite `$id` |
| user_id | string | Who recorded the sighting |
| fish_id | string | Reference to `fish_individuals.fish_id` |
| job_id | string | Reference to originating job |
| species_slug | string | Species identifier slug |
| species_common | string | Common name (English) |
| species_latin | string | Scientific name |
| species_czech | string | Czech name |
| area_code | string | Fishing area code |
| area_name | string | Fishing area name |
| captured_at | string | ISO 8601 when fish was filmed |
| created_at | string | ISO 8601 document creation |
| latitude | double | Capture location lat |
| longitude | double | Capture location lng |
| size_cm | double | Estimated size in cm |
| confidence | double | AI confidence 0.0-1.0 |
| is_new_fish | boolean | True if this created a new fish_individual |
| xp_earned | integer | XP awarded for this sighting |
| rarity | enum | `common` / `uncommon` / `rare` / `legendary` |
| raw_video_file_id | string | Original video file ID |
| primary_frame_file_id | string | Best frame file ID |
| frame_file_ids | array[string] | All extracted frame file IDs |
| created_by_ai | boolean | True if AI-created (vs manual entry) |
| manual_reviewed | boolean | Whether a researcher reviewed this |
| notes | string | Additional notes |

**Indexes:**
- `sighting_id` (unique, primary)
- `user_id` (key)
- `fish_id` (key)
- `species_slug` (key)
- `area_code` (key)
- `user_id + species_slug` (composite, for user's species list)
- `captured_at` (descending)
- `rarity` (key)

---

### 4. fish_individuals

A unique fish individual tracked over time via re-identification.

| Field | Type | Description |
|-------|------|-------------|
| fish_id | string (PK) | Format: `CZ-{area}-{ABBREV}-{NNNN}` (e.g. `CZ-471011-CRP-0042`) |
| species_slug | string | Species identifier |
| species_common | string | Common name (English) |
| species_latin | string | Scientific name |
| species_czech | string | Czech name |
| area_code | string | Primary area code |
| area_name | string | Primary area name |
| rarity | enum | `common` / `uncommon` / `rare` / `legendary` |
| first_seen_by | string | user_id of first observer |
| first_sighting_id | string | Reference to first sighting |
| first_seen_at | string | ISO 8601 |
| last_sighting_id | string | Reference to most recent sighting |
| last_seen_at | string | ISO 8601 |
| total_sightings | integer | How many times this fish was seen |
| estimated_size_cm | double | Current estimated size |
| max_size_cm | double | Largest recorded measurement |
| reference_frame_file_id | string | Best reference image file ID |
| created_at | string | ISO 8601 |
| updated_at | string | ISO 8601 |

**Indexes:**
- `fish_id` (unique, primary)
- `species_slug` (key)
- `area_code` (key)
- `rarity` (key)
- `first_seen_by` (key)
- `total_sightings` (descending)

---

### 5. media_files

Registry of all files stored in Appwrite Storage.

| Field | Type | Description |
|-------|------|-------------|
| media_id | string (PK) | Appwrite `$id` |
| owner_user_id | string | Who uploaded |
| sighting_id | string | Associated sighting (nullable) |
| fish_id | string | Associated fish individual (nullable) |
| bucket_id | string | Appwrite Storage bucket ID |
| file_id | string | Appwrite Storage file ID |
| media_type | enum | `video` / `image` |
| purpose | enum | `raw_capture` / `processed_frame` / `reference` / `avatar` |
| mime_type | string | e.g. `video/mp4`, `image/jpeg` |
| size_bytes | integer | File size |
| created_at | string | ISO 8601 |

**Indexes:**
- `media_id` (unique, primary)
- `owner_user_id` (key)
- `sighting_id` (key)
- `fish_id` (key)
- `bucket_id + file_id` (composite, unique)
- `purpose` (key)

---

### 6. achievements

Definition table for all unlockable achievements.

| Field | Type | Description |
|-------|------|-------------|
| achievement_id | string (PK) | Appwrite `$id` |
| slug | string | Unique machine name (e.g. `first_catch`) |
| title_en | string | English title |
| title_cs | string | Czech title |
| description_en | string | English description |
| description_cs | string | Czech description |
| icon | string | Icon name or emoji |
| category | enum | `sightings` / `species` / `level` / `exploration` / `streaks` |
| threshold | integer | Value needed to unlock |
| xp_reward | integer | XP granted on unlock |

**Indexes:**
- `achievement_id` (unique, primary)
- `slug` (unique)
- `category` (key)

---

### 7. user_achievements

Join table tracking which users unlocked which achievements.

| Field | Type | Description |
|-------|------|-------------|
| id | string (PK) | Appwrite `$id` |
| user_id | string | Reference to `users.user_id` |
| achievement_id | string | Reference to `achievements.achievement_id` |
| unlocked_at | string | ISO 8601 when earned |

**Indexes:**
- `id` (unique, primary)
- `user_id` (key)
- `user_id + achievement_id` (composite, unique)
- `unlocked_at` (descending)

---

### 8. approval_requests

Researcher role approval workflow.

| Field | Type | Description |
|-------|------|-------------|
| request_id | string (PK) | Appwrite `$id` |
| user_id | string | Requesting user |
| username | string | Display name at time of request |
| institution | string | University/organization |
| reason | string | Why they need researcher access |
| status | enum | `pending` / `approved` / `rejected` |
| reviewed_by | string | Admin user_id who reviewed |
| reviewed_at | string | ISO 8601 |
| created_at | string | ISO 8601 |

**Indexes:**
- `request_id` (unique, primary)
- `user_id` (key)
- `status` (key, for admin queue)
- `created_at` (descending)

---

### 9. fishing_areas

Reference data for Czech fishing areas (reviry).

| Field | Type | Description |
|-------|------|-------------|
| area_id | string (PK) | Appwrite `$id` |
| code | string | Official area code (e.g. `471 011`) |
| code_clean | string | Code without spaces (e.g. `471011`) |
| name | string | Area name |
| latitude | double | Center point lat |
| longitude | double | Center point lng |
| water_type | string | River/lake/pond/reservoir |
| region | string | Czech region |
| url | string | Link to official page |

**Indexes:**
- `area_id` (unique, primary)
- `code_clean` (unique)
- `name` (fulltext)
- `water_type` (key)
- `region` (key)

---

### 10. leaderboards

Denormalized leaderboard snapshot for fast queries.

| Field | Type | Description |
|-------|------|-------------|
| id | string (PK) | Appwrite `$id` |
| user_id | string | Reference to `users.user_id` |
| username | string | Cached display name |
| total_xp | integer | Cached XP |
| level | integer | Cached level |
| total_sightings | integer | Cached sighting count |
| unique_species | integer | Cached species count |
| updated_at | string | ISO 8601 last refresh |

**Indexes:**
- `id` (unique, primary)
- `user_id` (unique)
- `total_xp` (descending)
- `total_sightings` (descending)
- `unique_species` (descending)
- `level` (descending)

---

## Storage Buckets

| Bucket ID | Purpose | Max File Size | Allowed Types |
|-----------|---------|---------------|---------------|
| `capture_raw_videos` | Raw underwater video from Flutter | 100 MB | `video/mp4`, `video/quicktime` |
| `capture_frames` | AI-extracted best frames | 10 MB | `image/jpeg`, `image/png` |
| `fish_reference_images` | Reference images for fish individuals | 10 MB | `image/jpeg`, `image/png` |
| `user_avatars` | User profile pictures | 5 MB | `image/jpeg`, `image/png`, `image/webp` |
| `exports` | Generated reports/exports | 50 MB | `application/pdf`, `text/csv`, `application/json` |

---

## Notes

- All collections use Appwrite Database with document-level permissions
- `$id` is auto-generated by Appwrite unless explicitly set (e.g. `fish_id` uses custom format)
- Realtime subscriptions are available on all collections via Appwrite Realtime
- Soft deletes are not used; documents are hard-deleted when needed
- `updated_at` is maintained by the application layer on every write
