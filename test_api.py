#!/usr/bin/env python3
"""
Test script for the Meeting Intelligence Platform API.
"""

import requests
import time
import sys
from pathlib import Path

API_URL = "http://localhost:8000"

def test_health():
    """Test health endpoint."""
    print("\n1️⃣  Testing health endpoint...")
    try:
        response = requests.get(f"{API_URL}/health", timeout=2)
        if response.status_code == 200:
            print("✓ Health check passed")
            return True
        else:
            print(f"✗ Health check failed: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"✗ Cannot connect to API at {API_URL}")
        print("  Make sure the server is running: python run_server.py")
        return False

def test_endpoints_info():
    """Test root endpoint."""
    print("\n2️⃣  Testing endpoints info...")
    try:
        response = requests.get(f"{API_URL}/", timeout=2)
        if response.status_code == 200:
            data = response.json()
            print("✓ API info retrieved")
            print(f"  Available endpoints: {list(data['endpoints'].keys())}")
            return True
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_job_listing():
    """Test job listing endpoint."""
    print("\n3️⃣  Testing job listing...")
    try:
        response = requests.get(f"{API_URL}/api/v1/jobs", timeout=2)
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Jobs retrieved (Total: {data['total']})")
            return True
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_invalid_upload():
    """Test upload with invalid file."""
    print("\n4️⃣  Testing invalid file upload...")
    try:
        files = {"file": ("test.txt", "This is not a video")}
        response = requests.post(
            f"{API_URL}/api/v1/videos/upload",
            files=files,
            timeout=2
        )
        if response.status_code == 400:
            print("✓ Invalid file rejected correctly")
            return True
        else:
            print(f"✗ Expected 400, got {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_with_sample_video():
    """Test with a sample video if available."""
    print("\n5️⃣  Checking for sample video...")
    
    # Look for sample video
    sample_videos = [
        "data/videos/sample.mp4",
        "data/videos/test.mp4",
        "sample.mp4"
    ]
    
    video_file = None
    for path in sample_videos:
        if Path(path).exists():
            video_file = path
            break
    
    if not video_file:
        print("⚠️  No sample video found (optional test)")
        print("  Create one and place it in data/videos/ to test video processing")
        return True
    
    print(f"\n  Found sample video: {video_file}")
    print("  Uploading for processing...")
    
    try:
        with open(video_file, "rb") as f:
            files = {"file": f}
            params = {"whisper_model": "tiny"}  # Use tiny model for testing
            response = requests.post(
                f"{API_URL}/api/v1/videos/upload",
                files=files,
                params=params,
                timeout=60
            )
        
        if response.status_code == 200:
            result = response.json()
            job_id = result["job_id"]
            status = result["status"]
            
            print(f"✓ Video uploaded (Job ID: {job_id})")
            print(f"  Status: {status}")
            
            if status == "completed":
                transcript = result.get("transcript", {})
                text_preview = transcript.get("text", "")[:100]
                print(f"  Transcript preview: {text_preview}...")
                return True
            elif status == "processing":
                print("  Processing is still running (expected for larger files)")
                return True
            else:
                print(f"  Unexpected status: {status}")
                return False
        else:
            error = response.json()
            print(f"✗ Upload failed: {error.get('detail', 'Unknown error')}")
            return False
            
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("🧪 Meeting Intelligence Platform - API Tests")
    print("="*60)
    
    results = []
    
    # Run tests
    results.append(("Health Check", test_health()))
    
    if not results[-1][1]:
        print("\n" + "="*60)
        print("❌ API is not running!")
        print("Start it with: python run_server.py")
        print("="*60 + "\n")
        return 1
    
    results.append(("Endpoints Info", test_endpoints_info()))
    results.append(("Job Listing", test_job_listing()))
    results.append(("Invalid Upload", test_invalid_upload()))
    results.append(("Sample Video", test_with_sample_video()))
    
    # Summary
    print("\n" + "="*60)
    print("📊 Test Summary")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓" if result else "✗"
        print(f"{status} {test_name}")
    
    print(f"\nPassed: {passed}/{total}")
    print("="*60 + "\n")
    
    if passed == total:
        print("✅ All tests passed! API is working correctly.")
        print("\nNext steps:")
        print("1. Upload a video using the web interface:")
        print("   Open static/upload.html in your browser")
        print("\n2. Or use the interactive API docs:")
        print(f"   {API_URL}/docs")
        return 0
    else:
        print("❌ Some tests failed. Please check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
