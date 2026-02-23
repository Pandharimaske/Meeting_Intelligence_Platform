from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path
import uuid
import shutil
from datetime import datetime
from typing import Optional

from src.audio_extraction.extractor import extract_audio_from_video
from src.audio_to_text.converter import convert_audio_to_text

# Create FastAPI instance
app = FastAPI(
    title="Meeting Intelligence Platform API",
    description="API for processing videos to extract audio and generate transcripts",
    version="0.1.0"
)

# Mount static files
static_path = Path(__file__).parent.parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Create directories if they don't exist
Path("data/video").mkdir(parents=True, exist_ok=True)
Path("data/audio").mkdir(parents=True, exist_ok=True)
Path("data/transcripts").mkdir(parents=True, exist_ok=True)
Path("data/jobs").mkdir(parents=True, exist_ok=True)

# Store job states in memory (in production, use a database)
jobs = {}


class VideoUploadRequest(BaseModel):
    """Request model for video upload parameters."""
    whisper_model: str = "base"
    enable_diarization: bool = False
    huggingface_token: Optional[str] = None


class ProcessingResponse(BaseModel):
    """Response model for processing status."""
    job_id: str
    status: str
    video_name: Optional[str] = None
    transcript: Optional[dict] = None
    error: Optional[str] = None


@app.get("/", tags=["Health"])
async def root():
    """Root endpoint - API information."""
    return {
        "name": "Meeting Intelligence Platform API",
        "version": "0.1.0",
        "description": "Process videos to extract audio and generate transcripts",
        "endpoints": {
            "health": "/health",
            "upload": "/api/v1/videos/upload",
            "status": "/api/v1/jobs/{job_id}",
            "transcript": "/api/v1/transcripts/{job_id}"
        }
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/api/v1/videos/upload", response_model=ProcessingResponse, tags=["Videos"])
async def upload_video(
    file: UploadFile = File(...),
    whisper_model: str = Query("base", pattern="^(tiny|base|small|medium|large)$"),
    enable_diarization: bool = Query(False),
    huggingface_token: Optional[str] = Query(None)
):
    """
    Upload a video file and process it to extract audio and generate transcript.

    Args:
        file: Video file to upload (mp4, mov, avi, mkv, etc.)
        whisper_model: Whisper model size (tiny, base, small, medium, large)
        enable_diarization: Enable speaker diarization
        huggingface_token: HuggingFace API token for diarization

    Returns:
        Processing status with job ID
    """
    # BUG FIX: initialise job_id before try block so the outer except can reference it safely
    job_id = None

    try:
        # Validate file
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")

        # Check file extension
        valid_extensions = {".mp4", ".mov", ".avi", ".mkv", ".flv", ".wmv", ".webm"}
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in valid_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid video format. Supported: {', '.join(valid_extensions)}"
            )

        # Create job ID and save video
        job_id = str(uuid.uuid4())
        video_dir = Path("data/video") / job_id
        video_dir.mkdir(parents=True, exist_ok=True)

        video_path = video_dir / file.filename

        # Save uploaded file
        with open(video_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Initialize job
        jobs[job_id] = {
            "status": "processing",
            "video_name": file.filename,
            "created_at": datetime.utcnow().isoformat(),
            "whisper_model": whisper_model,
            "diarization_enabled": enable_diarization,
            "transcript": None,
            "error": None
        }

        # Process video
        try:
            # Extract audio
            audio_path = extract_audio_from_video(str(video_path), output_dir="data/audio")

            # Convert to text
            transcript = convert_audio_to_text(
                audio_path,
                model_size=whisper_model,
                output_dir=str(video_dir / "transcripts"),
                enable_diarization=enable_diarization,
                huggingface_token=huggingface_token
            )

            # Update job status
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["transcript"] = transcript
            jobs[job_id]["completed_at"] = datetime.utcnow().isoformat()

        except Exception as e:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = str(e)
            raise

        return ProcessingResponse(
            job_id=job_id,
            status=jobs[job_id]["status"],
            video_name=file.filename,
            transcript=transcript if jobs[job_id]["status"] == "completed" else None,
            error=jobs[job_id]["error"]
        )

    except HTTPException:
        raise
    except Exception as e:
        if job_id and job_id in jobs:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = str(e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/jobs/{job_id}", response_model=ProcessingResponse, tags=["Jobs"])
async def get_job_status(job_id: str):
    """
    Get the status of a processing job.

    Args:
        job_id: Job ID returned from upload endpoint

    Returns:
        Job status and results
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    job = jobs[job_id]
    return ProcessingResponse(
        job_id=job_id,
        status=job["status"],
        video_name=job.get("video_name"),
        transcript=job.get("transcript"),
        error=job.get("error")
    )


@app.get("/api/v1/transcripts/{job_id}", tags=["Transcripts"])
async def get_transcript(job_id: str, format: str = Query("json", pattern="^(json|txt)$")):
    """
    Download transcript for a completed job.

    Args:
        job_id: Job ID
        format: Output format (json or txt)

    Returns:
        Transcript file or JSON response
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    job = jobs[job_id]
    if job["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Job status is '{job['status']}', not completed"
        )

    transcript = job.get("transcript")
    if not transcript:
        raise HTTPException(status_code=404, detail="No transcript found")

    if format == "json":
        return JSONResponse(content=transcript)
    else:  # txt
        text_file = Path(transcript.get("text_file"))
        if text_file.exists():
            return FileResponse(text_file, media_type="text/plain")
        else:
            raise HTTPException(status_code=404, detail="Transcript file not found")


@app.get("/api/v1/jobs", tags=["Jobs"])
async def list_jobs(status: Optional[str] = Query(None)):
    """
    List all jobs with optional status filter.

    Args:
        status: Filter by status (processing, completed, failed)

    Returns:
        List of jobs
    """
    filtered_jobs = []
    for job_id, job in jobs.items():
        if status is None or job["status"] == status:
            filtered_jobs.append({
                "job_id": job_id,
                "status": job["status"],
                "video_name": job.get("video_name"),
                "created_at": job.get("created_at"),
                "completed_at": job.get("completed_at"),
                "error": job.get("error")
            })

    return {"jobs": filtered_jobs, "total": len(filtered_jobs)}
