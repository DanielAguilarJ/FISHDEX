import time
import sys
import sqlite3
import json
from pathlib import Path
import httpx
import numpy as np
import cv2

BASE_URL = "http://127.0.0.1:8000"
SECRET = "change-me"  # matching settings.client_secret

def create_dummy_peces():
    """Create dummy JPG file for testing photo uploads."""
    img = np.ones((480, 640, 3), dtype=np.uint8) * 128
    # Draw a simple fish shape
    cv2.ellipse(img, (320, 240), (100, 40), 0, 0, 360, (0, 255, 0), -1)
    
    # We draw a tail polygon
    pts = np.array([[420, 240], [450, 210], [450, 270]], np.int32)
    cv2.fillPoly(img, [pts], (0, 255, 0))
    
    pez_path = Path("tests/dummy_pez.jpg")
    pez_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(pez_path), img)
    return pez_path

def main():
    print("=" * 70)
    print("FishDex E2E Linkage & Idempotency Integration Test")
    print(f"Target: {BASE_URL}")
    print("=" * 70)

    pez_file = create_dummy_peces()
    client = httpx.Client(headers={"X-FishDex-Client-Secret": SECRET})

    # Ensure uvicorn is running
    try:
        r = client.get(f"{BASE_URL}/health")
        assert r.status_code == 200
        print("✓ AI Server is responsive.")
    except Exception as e:
        print(f"✗ Failed to connect to server: {e}")
        sys.exit(1)

    # Clean previous local embeddings of Cyprinus carpio to ensure clean slate
    db_path = Path("data/embeddings/fishdex_embeddings.sqlite")
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        conn.execute("DELETE FROM fish_embeddings WHERE species_slug = 'cyprinus_carpio'")
        conn.commit()
        conn.close()
        print("✓ Cleaned previous test embeddings.")

    # 1. Test photo upload (first capture)
    print("\n--- 1. Uploading first photo capture (user_a, area 471-011) ---")
    files = {"file": ("pez_a.jpg", pez_file.read_bytes(), "image/jpeg")}
    data = {
        "user_id": "user_a",
        "area_code": "471-011",
        "area_name": "Moldava River",
        "latitude": "50.087",
        "longitude": "14.421",
        "species_slug": "cyprinus_carpio",
        "size_cm": "45.5",
        "weather": "sunny",
        "bite": "worm",
        "fish_state": "healthy",
        "custom_name": "Goldie",
        "notes": "First catch of Goldie"
    }
    
    r = client.post(f"{BASE_URL}/api/v1/jobs/upload", files=files, data=data)
    assert r.status_code == 200, f"Upload failed: {r.text}"
    job_id_1 = r.json()["job_id"]
    print(f"✓ Job 1 uploaded successfully. ID: {job_id_1}")

    # 2. Process job 1
    print("\n--- 2. Triggering processing of Job 1 ---")
    r = client.post(f"{BASE_URL}/api/v1/jobs/{job_id_1}/process")
    assert r.status_code == 202, f"Trigger failed: {r.text}"
    
    # Poll for completion
    print("Polling job 1 status...")
    status = "uploaded"
    for _ in range(30):
        time.sleep(1)
        r = client.get(f"{BASE_URL}/api/v1/jobs/{job_id_1}")
        status = r.json().get("status")
        if status in ("completed", "failed", "needs_review"):
            break
    print(f"Job 1 completed with status: {status}")
    assert status == "completed", f"Job 1 did not complete successfully: {r.json()}"

    # Get results of Job 1
    r = client.get(f"{BASE_URL}/api/v1/jobs/{job_id_1}/result")
    assert r.status_code == 200
    res_1 = r.json()
    fish_id_1 = res_1["fish_id"]
    print(f"✓ Sighting 1 details:")
    print(f"  - Fish ID: {fish_id_1}")
    print(f"  - Sighting ID: {res_1['id']}")
    print(f"  - Is New Fish: {res_1['is_new_fish']}")
    print(f"  - Preview Filename: {res_1['preview_filename']}")
    
    assert res_1["is_new_fish"] == 1
    assert res_1["catch_number"] == 1
    assert res_1["area_code"] == "471011"  # Normalized!
    assert res_1["media_type"] == "image"  # Detected!

    # 3. Test Idempotency (process job 1 again)
    print("\n--- 3. Testing Double Idempotency (re-process Job 1) ---")
    r = client.post(f"{BASE_URL}/api/v1/jobs/{job_id_1}/process")
    # Verify no duplicate sighting was added in SQLite
    conn = sqlite3.connect("data/fishdex_local.sqlite")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM fish_sightings WHERE job_id = ?", (job_id_1,))
    count = c.fetchone()[0]
    print(f"✓ Sightings count in SQLite for Job 1: {count}")
    assert count == 1, "Idempotency failed: duplicate sightings row in database!"

    c.execute("SELECT total_sightings FROM fish_individuals WHERE fish_id = ?", (fish_id_1,))
    total_sightings = c.fetchone()["total_sightings"]
    print(f"✓ Total sightings count for {fish_id_1}: {total_sightings}")
    assert total_sightings == 1, "Idempotency failed: individual total_sightings incremented!"
    conn.close()

    # 4. Area Code Normalization Folders Verification
    print("\n--- 4. Checking normalized directory structures on disk ---")
    # Normalized area_code is 471011
    media_dir = Path("data/storage/fish_media/471011")
    docs_dir = Path("data/private/fish_documents/471011")
    
    print(f"  - Normalized media dir exists: {media_dir.exists()}")
    print(f"  - Normalized private docs dir exists: {docs_dir.exists()}")
    
    assert media_dir.exists(), "Normalized media directory does not exist!"
    assert docs_dir.exists(), "Normalized private documents directory does not exist!"
    
    # 5. Test photo recapture by another user (user_b, same location, same species)
    print("\n--- 5. Uploading second capture (recapture by user_b, area 471 011) ---")
    files = {"file": ("pez_b.jpg", pez_file.read_bytes(), "image/jpeg")}
    data = {
        "user_id": "user_b",
        "area_code": "471 011",  # spacing variant
        "area_name": "Moldava River Upper",
        "latitude": "50.088",   # GPS extremely close (nearby)
        "longitude": "14.422",
        "species_slug": "cyprinus_carpio",
        "size_cm": "48.2",       # fish grew!
        "weather": "cloudy",
        "bite": "spinner",
        "fish_state": "released",
        "custom_name": "Goldie Recaught",
        "notes": "Recaptured Goldie one week later"
    }

    r = client.post(f"{BASE_URL}/api/v1/jobs/upload", files=files, data=data)
    assert r.status_code == 200
    job_id_2 = r.json()["job_id"]
    print(f"✓ Job 2 uploaded successfully. ID: {job_id_2}")

    # Process job 2
    print("\n--- 6. Triggering processing of Job 2 (Recapture) ---")
    r = client.post(f"{BASE_URL}/api/v1/jobs/{job_id_2}/process")
    assert r.status_code == 202
    
    # Poll for completion
    print("Polling job 2 status...")
    status = "uploaded"
    for _ in range(30):
        time.sleep(1)
        r = client.get(f"{BASE_URL}/api/v1/jobs/{job_id_2}")
        status = r.json().get("status")
        if status in ("completed", "failed", "needs_review"):
            break
    print(f"Job 2 completed with status: {status}")
    assert status == "completed", f"Job 2 did not complete successfully: {r.json()}"

    # Get results of Job 2
    r = client.get(f"{BASE_URL}/api/v1/jobs/{job_id_2}/result")
    assert r.status_code == 200
    res_2 = r.json()
    fish_id_2 = res_2["fish_id"]
    
    print(f"✓ Sighting 2 details:")
    print(f"  - Fish ID: {fish_id_2}")
    print(f"  - Sighting ID: {res_2['id']}")
    print(f"  - Is New Fish: {res_2['is_new_fish']}")
    print(f"  - Catch Number: {res_2['catch_number']}")
    print(f"  - Previous Sighting ID: {res_2['previous_sighting_id']}")
    print(f"  - Total Sightings Before: {res_2['total_sightings_before']}")
    print(f"  - Total Sightings After: {res_2['total_sightings_after']}")
    
    linkage = json.loads(res_2["linkage_json"])
    print(f"  - Linkage Decision: {linkage.get('decision')}")
    print(f"  - Match Confidence: {linkage.get('match_confidence')}")
    
    assert fish_id_2 == fish_id_1, "Failed linkage: recapture was assigned a new fish ID!"
    assert res_2["is_new_fish"] == 0, "Failed linkage: recapture was marked as is_new_fish!"
    assert res_2["catch_number"] == 2, "Incorrect catch numbering!"
    assert res_2["previous_sighting_id"] == res_1["id"], "Incorrect previous sighting pointer!"
    assert res_2["total_sightings_before"] == 1
    assert res_2["total_sightings_after"] == 2

    # 6. Verify fish_index.json post-commit file
    print("\n--- 7. Verifying fish_index.json file contents ---")
    index_file_path = docs_dir / "cyprinus_carpio" / fish_id_1 / "fish_index.json"
    print(f"  - fish_index.json path: {index_file_path}")
    assert index_file_path.exists(), "fish_index.json does not exist!"
    
    index_data = json.loads(index_file_path.read_text(encoding="utf-8"))
    print(f"  - Total captures in index: {index_data['total_captures']}")
    assert index_data["total_captures"] == 2
    assert index_data["captures"][0]["catch_number"] == 1
    assert index_data["captures"][1]["catch_number"] == 2
    print("✓ fish_index.json matches expected schema and contains both entries.")

    # 7. Test Timeline Endpoint
    print("\n--- 8. Testing Timeline Endpoint /dashboard/fish/{fish_id}/timeline ---")
    r = client.get(f"{BASE_URL}/api/v1/dashboard/fish/{fish_id_1}/timeline?secret=change-me")
    assert r.status_code == 200
    timeline_res = r.json()
    print(f"✓ Timeline events found: {timeline_res['total_captures']}")
    assert timeline_res["total_captures"] == 2
    
    events = timeline_res["timeline"]
    assert events[0]["catch_number"] == 1
    assert events[1]["catch_number"] == 2
    assert events[0]["user_id"] == "user_a"
    assert events[1]["user_id"] == "user_b"
    assert events[1]["previous_sighting_id"] == events[0]["id"]
    print("✓ Timeline returned chronological events correctly.")

    print("\n" + "=" * 70)
    print("ALL TESTS PASSED SUCCESSFULLY! linkage, normalization, double idempotency verified!")
    print("=" * 70)

    # Clean dummy pez
    if pez_file.exists():
        pez_file.unlink()

if __name__ == "__main__":
    main()
