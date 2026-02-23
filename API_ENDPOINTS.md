# FastAPI Endpoints

## Overview
The Meeting Intelligence Platform provides REST API endpoints for processing videos to extract audio and generate transcripts.

## Running the Server

```bash
# Start the FastAPI server
python run_server.py
```

The API will be available at:
- **Base URL**: `http://localhost:8000`
- **Interactive Docs**: `http://localhost:8000/docs` (Swagger UI)
- **Alternative Docs**: `http://localhost:8000/redoc` (ReDoc)

---

## Endpoints

### 1. Health Check

**GET** `/health`

Check if the API is running.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-02-17T10:30:00.000000"
}
```

---

### 2. Upload Video & Process

**POST** `/api/v1/videos/upload`

Upload a video file and process it to extract audio and generate transcript.

**Parameters:**
- `file` (file, required): Video file (mp4, mov, avi, mkv, flv, wmv, webm)
- `whisper_model` (string, optional): Model size - `tiny`, `base`, `small`, `medium`, `large` (default: `base`)
- `enable_diarization` (boolean, optional): Enable speaker diarization (default: `false`)
- `huggingface_token` (string, optional): HuggingFace token for diarization

**cURL Example:**
```bash
curl -X POST "http://localhost:8000/api/v1/videos/upload" \
  -F "file=@meeting.mp4" \
  -F "whisper_model=base" \
  -F "enable_diarization=true" \
  -F "huggingface_token=hf_xxx"
```

**Python Example:**
```python
import requests

with open("meeting.mp4", "rb") as f:
    response = requests.post(
        "http://localhost:8000/api/v1/videos/upload",
        files={"file": f},
        params={
            "whisper_model": "base",
            "enable_diarization": True,
            "huggingface_token": "hf_xxx"
        }
    )
    
print(response.json())
```

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "video_name": "meeting.mp4",
  "transcript": {
    "text": "Hello, welcome to the meeting...",
    "text_file": "data/jobs/...",
    "json_file": "data/jobs/...",
    "language": "en",
    "segments": [...],
    "speaker_segments": [
      {
        "speaker": "Speaker 0",
        "text": "Hello, welcome to the meeting..."
      }
    ],
    "speakers": {
      "Speaker 0": {
        "total_duration": 45.5,
        "segment_count": 5
      }
    },
    "total_speakers": 1,
    "diarization_enabled": true
  },
  "error": null
}
```

---

### 3. Get Job Status

**GET** `/api/v1/jobs/{job_id}`

Get the current status and results of a processing job.

**Parameters:**
- `job_id` (string, path): Job ID from upload response

**cURL Example:**
```bash
curl "http://localhost:8000/api/v1/jobs/550e8400-e29b-41d4-a716-446655440000"
```

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "video_name": "meeting.mp4",
  "transcript": {...},
  "error": null
}
```

**Status Values:**
- `processing` - Job is currently processing
- `completed` - Job completed successfully
- `failed` - Job failed with error

---

### 4. Download Transcript

**GET** `/api/v1/transcripts/{job_id}`

Download the transcript for a completed job.

**Parameters:**
- `job_id` (string, path): Job ID
- `format` (string, query): Output format - `json` or `txt` (default: `json`)

**cURL Examples:**
```bash
# Download as JSON
curl "http://localhost:8000/api/v1/transcripts/550e8400-e29b-41d4-a716-446655440000?format=json" \
  -o transcript.json

# Download as TXT
curl "http://localhost:8000/api/v1/transcripts/550e8400-e29b-41d4-a716-446655440000?format=txt" \
  -o transcript.txt
```

---

### 5. List Jobs

**GET** `/api/v1/jobs`

List all processing jobs with optional filtering.

**Parameters:**
- `status` (string, optional): Filter by status - `processing`, `completed`, `failed`

**cURL Examples:**
```bash
# List all jobs
curl "http://localhost:8000/api/v1/jobs"

# List only completed jobs
curl "http://localhost:8000/api/v1/jobs?status=completed"

# List only failed jobs
curl "http://localhost:8000/api/v1/jobs?status=failed"
```

**Response:**
```json
{
  "jobs": [
    {
      "job_id": "550e8400-e29b-41d4-a716-446655440000",
      "status": "completed",
      "video_name": "meeting.mp4",
      "created_at": "2026-02-17T10:30:00.000000",
      "completed_at": "2026-02-17T10:35:00.000000",
      "error": null
    }
  ],
  "total": 1
}
```

---

## Complete Workflow Example

```python
import requests
import time

# 1. Upload video
print("Uploading video...")
with open("meeting.mp4", "rb") as f:
    response = requests.post(
        "http://localhost:8000/api/v1/videos/upload",
        files={"file": f},
        params={"whisper_model": "base"}
    )

job_id = response.json()["job_id"]
print(f"Job ID: {job_id}")

# 2. Poll for status
print("Processing...")
while True:
    status_response = requests.get(f"http://localhost:8000/api/v1/jobs/{job_id}")
    status = status_response.json()["status"]
    
    if status == "completed":
        print("✓ Processing complete!")
        break
    elif status == "failed":
        error = status_response.json()["error"]
        print(f"✗ Processing failed: {error}")
        break
    else:
        print(f"  Status: {status}")
        time.sleep(2)

# 3. Download transcript
print("Downloading transcript...")
transcript = requests.get(
    f"http://localhost:8000/api/v1/transcripts/{job_id}",
    params={"format": "json"}
).json()

print("\n=== Transcript ===")
print(transcript["text"])

if transcript.get("speakers"):
    print("\n=== Speakers ===")
    for speaker, info in transcript["speakers"].items():
        print(f"{speaker}: {info['total_duration']:.1f}s")
```

---

## Error Handling

All endpoints return appropriate HTTP status codes:

- `200 OK` - Successful request
- `400 Bad Request` - Invalid file format or parameters
- `404 Not Found` - Job ID or resource not found
- `500 Internal Server Error` - Server error during processing

**Error Response:**
```json
{
  "detail": "Invalid video format. Supported: .mp4, .mov, .avi, .mkv, .flv, .wmv, .webm"
}
```

---

## Configuration

Edit the following in `run_server.py`:

```python
uvicorn.run(
    "app.api:app",
    host="0.0.0.0",        # Change to restrict IP access
    port=8000,             # Change port
    reload=True,           # Disable in production
    log_level="info"       # Change log level
)
```

---

## Notes

- Jobs are stored in memory. In production, use a database like PostgreSQL
- Large video files may take time to process
- Diarization requires a HuggingFace API token (get one at https://huggingface.co/settings/tokens)
- Supported video formats: mp4, mov, avi, mkv, flv, wmv, webm
