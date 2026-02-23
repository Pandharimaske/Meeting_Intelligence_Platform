# 🎬 Meeting Intelligence Platform - API Guide

## Quick Start

### 1. Install Dependencies

```bash
# Install all required packages
pip install -e .
```

Or use the setup script:
```bash
python setup.py
```

### 2. Start the API Server

```bash
python run_server.py
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

### 3. Access the API

**Interactive API Documentation (Recommended):**
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

**Web Upload Interface:**
- Open `static/upload.html` in your browser or
- Serve it with: `python -m http.server 8001` (then open http://localhost:8001/static/upload.html)

---

## API Endpoints Overview

### Health & Info
- `GET /health` - Server health check
- `GET /` - API information

### Video Processing
- `POST /api/v1/videos/upload` - Upload and process video
- `GET /api/v1/jobs/{job_id}` - Get job status
- `GET /api/v1/transcripts/{job_id}` - Download transcript
- `GET /api/v1/jobs` - List all jobs

---

## Usage Examples

### Example 1: Simple Upload with Web Interface

1. Open `static/upload.html` in your browser
2. Select a video file
3. Click "Upload & Process"
4. View results immediately

### Example 2: Command Line Upload

```bash
curl -X POST "http://localhost:8000/api/v1/videos/upload" \
  -F "file=@meeting.mp4" \
  -F "whisper_model=base"
```

### Example 3: With Speaker Diarization

```bash
curl -X POST "http://localhost:8000/api/v1/videos/upload" \
  -F "file=@meeting.mp4" \
  -F "whisper_model=base" \
  -F "enable_diarization=true" \
  -F "huggingface_token=hf_xxxxxxxxxxxxx"
```

Get your HuggingFace token: https://huggingface.co/settings/tokens

### Example 4: Python Client

```python
import requests

# Upload video
files = {"file": open("meeting.mp4", "rb")}
params = {
    "whisper_model": "base",
    "enable_diarization": True,
    "huggingface_token": "hf_xxx"
}

response = requests.post(
    "http://localhost:8000/api/v1/videos/upload",
    files=files,
    params=params
)

result = response.json()
job_id = result["job_id"]

print(f"Job ID: {job_id}")
print(f"Status: {result['status']}")
print(f"Transcript: {result['transcript']['text']}")
```

### Example 5: Check Job Status

```bash
curl "http://localhost:8000/api/v1/jobs/550e8400-e29b-41d4-a716-446655440000"
```

### Example 6: Download Transcript

```bash
# As JSON
curl -o transcript.json \
  "http://localhost:8000/api/v1/transcripts/550e8400-e29b-41d4-a716-446655440000?format=json"

# As plain text
curl -o transcript.txt \
  "http://localhost:8000/api/v1/transcripts/550e8400-e29b-41d4-a716-446655440000?format=txt"
```

---

## Response Structure

### Transcript Response

```json
{
  "text": "Full transcript text here...",
  "text_file": "data/jobs/.../meeting.txt",
  "json_file": "data/jobs/.../meeting.json",
  "language": "en",
  "segments": [
    {
      "id": 0,
      "seek": 0,
      "start": 0.0,
      "end": 2.5,
      "text": "Hello there",
      "tokens": [...],
      "temperature": 0.0,
      "avg_logprob": -0.34,
      "compression_ratio": 1.5,
      "speaker": "Speaker 0"
    }
  ],
  "speaker_segments": [
    {
      "speaker": "Speaker 0",
      "text": "Hello there, welcome to the meeting"
    }
  ],
  "speakers": {
    "Speaker 0": {
      "total_duration": 45.5,
      "segment_count": 12
    },
    "Speaker 1": {
      "total_duration": 32.3,
      "segment_count": 8
    }
  },
  "total_speakers": 2,
  "diarization_enabled": true
}
```

---

## Configuration

### Server Options (in `run_server.py`)

```python
uvicorn.run(
    "app.api:app",
    host="0.0.0.0",           # Listen on all interfaces
    port=8000,                # Change port
    reload=True,              # Auto-reload on code changes (disable in production)
    log_level="info"          # DEBUG, INFO, WARNING, ERROR, CRITICAL
)
```

### Whisper Models

- **tiny** (39M) - Fastest, 4-5% WER (Word Error Rate)
- **base** (74M) - Recommended, 8% WER
- **small** (244M) - Better accuracy, 16% WER
- **medium** (769M) - High accuracy, 25% WER
- **large** (1.5B) - Best accuracy, 25% WER

---

## Directory Structure

```
Meeting_Intelligence_Platform/
├── app/
│   ├── __init__.py
│   └── api.py                 # FastAPI endpoints
├── src/
│   ├── audio_extraction/
│   │   ├── __init__.py
│   │   └── extractor.py       # Audio extraction from video
│   ├── audio_to_text/
│   │   ├── __init__.py
│   │   └── converter.py       # Whisper transcription
│   └── diarization/
│       ├── __init__.py
│       └── speaker_diarization.py  # Speaker identification
├── data/
│   ├── videos/                # Uploaded videos
│   ├── audio/                 # Extracted audio
│   ├── transcripts/           # Generated transcripts
│   └── jobs/                  # Job data
├── static/
│   └── upload.html            # Web upload interface
├── main.py                    # CLI interface
├── run_server.py              # Start API server
├── setup.py                   # Setup script
├── pyproject.toml             # Dependencies
└── API_ENDPOINTS.md           # Detailed API docs
```

---

## Troubleshooting

### Server won't start

```bash
# Check if port 8000 is in use
lsof -i :8000

# Use a different port
# Edit run_server.py and change port=8000 to port=8001
```

### CORS issues

```python
# Add this to app.py if needed:
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Import errors

```bash
# Make sure you're in the project root directory
cd /Users/pandhari/Desktop/Meeting_Intelligence_Platform

# Reinstall packages
pip install --force-reinstall -e .
```

### Video processing fails

1. Check video format is supported (mp4, mov, avi, mkv)
2. Ensure FFmpeg is installed: `brew install ffmpeg` (macOS)
3. Check video file is not corrupted

### Diarization not working

1. Verify HuggingFace token is valid
2. Check internet connection
3. Ensure `pyannote.audio` is installed: `pip install pyannote.audio`

---

## Production Deployment

### Using Gunicorn

```bash
pip install gunicorn

gunicorn app.api:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --access-logfile - \
  --error-logfile -
```

### Using Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY . .
RUN pip install -e .

EXPOSE 8000

CMD ["python", "run_server.py"]
```

### Environment Variables

Create `.env` file:
```
HUGGINGFACE_TOKEN=hf_xxxxxxxxxxxxx
WHISPER_MODEL_SIZE=base
LOG_LEVEL=info
```

---

## Support

- **Issues?** Check [API_ENDPOINTS.md](API_ENDPOINTS.md)
- **Swagger Docs:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
