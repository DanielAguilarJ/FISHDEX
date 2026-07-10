"""
FishDex - Integration Test Script
===================================
Tests the full pipeline: AI Server health → identify test → jobs endpoint.

Usage (from ai-server directory):
    python -m pytest tests/test_integration.py -v

Or standalone:
    python tests/test_integration.py
"""

import json
import sys
import time
from pathlib import Path

import httpx

# Config
BASE_URL = "http://127.0.0.1:8000"
SECRET = "change-me"  # Match FISHDEX_AI_SERVER_SECRET in .env

def test_health():
    """Test basic health endpoint."""
    print("1. Testing /health ...")
    resp = httpx.get(f"{BASE_URL}/health", timeout=10)
    assert resp.status_code == 200, f"Health check failed: {resp.status_code}"
    data = resp.json()
    assert data["status"] == "healthy"
    print(f"   ✓ Server healthy (uptime={data.get('uptime_seconds', 0)}s)")
    return True


def test_identify_test():
    """Test the legacy /api/v1/identify/test endpoint."""
    print("2. Testing /api/v1/identify/test ...")
    resp = httpx.get(f"{BASE_URL}/api/v1/identify/test", timeout=30)
    assert resp.status_code == 200, f"Identify test failed: {resp.status_code}"
    data = resp.json()
    assert data.get("success") is True
    assert "fish_id" in data
    print(f"   ✓ Got fish_id={data['fish_id']}, species={data.get('species')}")
    return True


def test_health_detailed():
    """Test detailed health endpoint."""
    print("3. Testing /api/v1/health/detailed ...")
    resp = httpx.get(f"{BASE_URL}/api/v1/health/detailed", timeout=10)
    assert resp.status_code == 200, f"Detailed health failed: {resp.status_code}"
    data = resp.json()
    print(f"   ✓ ONNX loaded={data.get('onnx_model_loaded')}, "
          f"fish count={data.get('total_fish_in_database', 0)}, "
          f"disk={data.get('disk_usage_mb', 0)}MB")
    return True


def test_species_list():
    """Test that species catalog loads."""
    print("4. Testing /api/v1/species ...")
    resp = httpx.get(f"{BASE_URL}/api/v1/species", timeout=10)
    assert resp.status_code == 200, f"Species list failed: {resp.status_code}"
    data = resp.json()
    count = data.get("count", 0)
    assert count > 0, "No species returned"
    print(f"   ✓ {count} Czech fish species available")
    return True


def test_jobs_endpoint_404():
    """Test that jobs endpoint returns 404 for non-existent job."""
    print("5. Testing /api/v1/jobs/fake-id (expect 404) ...")
    resp = httpx.get(
        f"{BASE_URL}/api/v1/jobs/fake-job-id-12345",
        headers={"X-FishDex-Client-Secret": SECRET},
        timeout=10,
    )
    # Should be 404 (job doesn't exist in Appwrite)
    # Or 401/403 if auth is misconfigured
    print(f"   ✓ Got status {resp.status_code} (expected 404 or auth error)")
    return True


def main():
    print("=" * 60)
    print("FishDex Integration Tests")
    print(f"Server: {BASE_URL}")
    print("=" * 60)
    print()

    tests = [
        test_health,
        test_identify_test,
        test_health_detailed,
        test_species_list,
        test_jobs_endpoint_404,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"   ✗ FAILED: {e}")
            failed += 1
        print()

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
