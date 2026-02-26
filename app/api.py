"""
Meeting Intelligence Platform — Full API

Pipeline per upload:
  1. Save file
  2. If video → extract audio
  3. Audio → Whisper transcript
  4. Transcript → semantic chunks
  5. Chunks → FAISS vector store
  6. Vector store + RAG → MoM (Minutes of Meeting)
  7. Vector store kept in memory for /chat endpoint
"""

import uuid
import shutil
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import settings
from src.audio_extraction.extractor import extract_audio_from_video
from src.audio_to_text.converter import convert_audio_to_text
from src.chunking.chunker import TranscriptChunker
from src.vector_store.store import MeetingVectorStore
from src.report_generation.rag_mom_generator import RAGMoMGenerator

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Meeting Intelligence Platform",
    description="Upload a meeting audio/video → get transcript, MoM, and chat with your meeting.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for the frontend
static_path = Path(__file__).parent.parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Ensure all data dirs exist
for d in [settings.video_dir, settings.audio_dir, settings.transcript_dir, settings.jobs_dir]:
    Path(d).mkdir(parents=True, exist_ok=True)

# Thread pool for CPU-bound work (Whisper, embeddings)
_executor = ThreadPoolExecutor(max_workers=2)

# ── In-memory state ───────────────────────────────────────────────────────────

# job_id → job dict
jobs: Dict[str, dict] = {}

# job_id → loaded MeetingVectorStore (for chat)
vector_stores: Dict[str, MeetingVectorStore] = {}


# ── Pydantic models ───────────────────────────────────────────────────────────

class JobStatus(BaseModel):
    job_id: str
    status: str          # uploaded | transcribing | chunking | indexing | generating_mom | completed | failed
    step: str            # human-readable current step
    progress: int        # 0-100
    filename: str
    file_type: str       # audio | video
    created_at: str
    completed_at: Optional[str] = None
    error: Optional[str] = None

class JobDetail(JobStatus):
    transcript_available: bool = False
    mom_available: bool = False
    chunk_count: int = 0
    duration_seconds: Optional[float] = None

class ChatRequest(BaseModel):
    question: str
    history: Optional[List[Dict]] = []   # [{"role": "user"|"assistant", "content": "..."}]

class ChatResponse(BaseModel):
    answer: str
    sources: List[Dict] = []   # retrieved chunks with timestamps


# ── Helper: build RAG generator from config ───────────────────────────────────

def _make_rag(store: MeetingVectorStore) -> RAGMoMGenerator:
    backend = settings.llm_backend
    api_key_map = {
        "openrouter": settings.openrouter_api_key,
        "anthropic":  settings.anthropic_api_key,
        "openai":     settings.openai_api_key,
    }
    return RAGMoMGenerator(
        vector_store=store,
        backend=backend,
        api_key=api_key_map.get(backend, ""),
        model=settings.get_llm_model(),
        base_url=settings.openrouter_base_url if backend == "openrouter" else None,
        top_k=settings.rag_top_k,
        score_threshold=settings.rag_score_threshold,
        max_tokens=settings.llm_max_tokens,
        temperature=settings.llm_temperature,
    )


# ── Pipeline (runs in thread pool) ───────────────────────────────────────────

def _run_pipeline(job_id: str, file_path: Path, file_type: str) -> None:
    """
    Full processing pipeline. Runs synchronously in a thread.
    Updates jobs[job_id] at each stage.
    """
    def update(status: str, step: str, progress: int):
        jobs[job_id].update({"status": status, "step": step, "progress": progress})

    try:
        job_dir = settings.jobs_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        # ── Step 1: Extract audio (video only) ──────────────────
        if file_type == "video":
            update("transcribing", "Extracting audio from video…", 10)
            audio_path = extract_audio_from_video(
                str(file_path), output_dir=str(settings.audio_dir)
            )
        else:
            audio_path = str(file_path)

        # ── Step 2: Transcribe ───────────────────────────────────
        update("transcribing", "Transcribing audio with Whisper…", 25)
        transcript = convert_audio_to_text(
            audio_path,
            model_size=settings.whisper_model,
            output_dir=str(job_dir / "transcripts"),
            enable_diarization=settings.enable_diarization,
            huggingface_token=settings.huggingface_token or None,
        )
        jobs[job_id]["transcript"] = transcript
        jobs[job_id]["transcript_available"] = True

        # Estimate duration from last segment
        segments = transcript.get("segments", [])
        if segments:
            jobs[job_id]["duration_seconds"] = segments[-1].get("end", 0)

        # ── Step 3: Chunk ────────────────────────────────────────
        update("chunking", "Splitting transcript into semantic chunks…", 50)
        chunker = TranscriptChunker(
            max_chunk_words=settings.chunk_max_words,
            overlap_segments=settings.chunk_overlap_segments,
        )
        chunks = chunker.chunk_from_segments(segments)
        jobs[job_id]["chunk_count"] = len(chunks)

        # Save chunks
        with open(job_dir / "chunks.json", "w") as f:
            json.dump(chunks, f, indent=2, default=str)

        # ── Step 4: Build vector store ───────────────────────────
        update("indexing", "Building semantic search index…", 65)
        store = MeetingVectorStore(model_name=settings.embedding_model)
        store.build(chunks)
        store.save(str(job_dir / "vector_store"))
        vector_stores[job_id] = store

        # ── Step 5: Generate MoM ─────────────────────────────────
        update("generating_mom", "Generating Minutes of Meeting…", 80)
        mom_path = str(job_dir / "mom.json")

        if settings.llm_backend == "template":
            # Lightweight fallback
            from src.report_generation.mom_generator import MoMGenerator
            gen = MoMGenerator(backend="template")
            mom = gen.generate(chunks, output_path=mom_path)
        else:
            rag = _make_rag(store)
            mom = rag.generate(output_path=mom_path)

        jobs[job_id]["mom"] = mom
        jobs[job_id]["mom_available"] = True

        # ── Done ─────────────────────────────────────────────────
        jobs[job_id].update({
            "status": "completed",
            "step": "Done",
            "progress": 100,
            "completed_at": datetime.utcnow().isoformat(),
        })

    except Exception as e:
        jobs[job_id].update({
            "status": "failed",
            "step": f"Failed: {str(e)}",
            "progress": 0,
            "error": str(e),
        })
        raise


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.get("/", tags=["Health"])
async def root():
    return {
        "name": "Meeting Intelligence Platform",
        "version": "1.0.0",
        "docs": "/docs",
        "frontend": "/static/index.html",
    }


# ── Upload ────────────────────────────────────────────────────────────────────

AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".flv", ".wmv", ".webm"}

@app.post("/api/v1/upload", tags=["Pipeline"])
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    """
    Upload an audio or video file. Returns a job_id immediately.
    Poll GET /api/v1/jobs/{job_id} to track progress.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")

    ext = Path(file.filename).suffix.lower()
    if ext in AUDIO_EXTENSIONS:
        file_type = "audio"
        save_dir = settings.audio_dir
    elif ext in VIDEO_EXTENSIONS:
        file_type = "video"
        save_dir = settings.video_dir
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. "
                   f"Audio: {', '.join(AUDIO_EXTENSIONS)}  "
                   f"Video: {', '.join(VIDEO_EXTENSIONS)}"
        )

    job_id = str(uuid.uuid4())
    save_path = Path(save_dir) / f"{job_id}{ext}"

    # Save file to disk
    with open(save_path, "wb") as buf:
        shutil.copyfileobj(file.file, buf)

    # Initialise job record
    jobs[job_id] = {
        "job_id":       job_id,
        "status":       "uploaded",
        "step":         "Queued for processing…",
        "progress":     5,
        "filename":     file.filename,
        "file_type":    file_type,
        "created_at":   datetime.utcnow().isoformat(),
        "completed_at": None,
        "error":        None,
        "transcript":   None,
        "mom":          None,
        "transcript_available": False,
        "mom_available":        False,
        "chunk_count":          0,
        "duration_seconds":     None,
    }

    # Run pipeline in background thread (non-blocking)
    loop = asyncio.get_event_loop()
    background_tasks.add_task(
        loop.run_in_executor, _executor, _run_pipeline, job_id, save_path, file_type
    )

    return {
        "job_id":    job_id,
        "status":    "uploaded",
        "filename":  file.filename,
        "file_type": file_type,
        "message":   "Processing started. Poll /api/v1/jobs/{job_id} for status.",
    }


# ── Jobs ──────────────────────────────────────────────────────────────────────

@app.get("/api/v1/jobs", tags=["Jobs"])
async def list_jobs(status: Optional[str] = None):
    """List all jobs, optionally filtered by status."""
    result = []
    for jid, job in jobs.items():
        if status is None or job["status"] == status:
            result.append(_job_summary(jid, job))
    return {"jobs": sorted(result, key=lambda j: j["created_at"], reverse=True), "total": len(result)}


@app.get("/api/v1/jobs/{job_id}", tags=["Jobs"])
async def get_job(job_id: str):
    """Get full status and metadata for a job."""
    job = _get_job_or_404(job_id)
    return _job_detail(job_id, job)


# ── Transcript ────────────────────────────────────────────────────────────────

@app.get("/api/v1/jobs/{job_id}/transcript", tags=["Transcript"])
async def get_transcript(job_id: str, fmt: str = "json"):
    """
    Get the transcript for a completed job.
    fmt: 'json' (full with segments+timestamps) | 'txt' (plain text)
    """
    job = _get_job_or_404(job_id)
    _require_completed(job_id, job)

    if not job.get("transcript_available"):
        raise HTTPException(status_code=404, detail="Transcript not yet available.")

    transcript = job.get("transcript", {})

    if fmt == "txt":
        return JSONResponse(content={"text": transcript.get("text", "")})

    # Full JSON with segments (timestamps preserved)
    return JSONResponse(content={
        "text":            transcript.get("text", ""),
        "language":        transcript.get("language", "en"),
        "segments":        transcript.get("segments", []),
        "speaker_segments": transcript.get("speaker_segments", []),
        "speakers":        transcript.get("speakers", {}),
        "total_speakers":  transcript.get("total_speakers", 0),
    })


# ── MoM ───────────────────────────────────────────────────────────────────────

@app.get("/api/v1/jobs/{job_id}/mom", tags=["MoM"])
async def get_mom(job_id: str):
    """
    Get the generated Minutes of Meeting for a completed job.
    All items include timestamp citations.
    """
    job = _get_job_or_404(job_id)
    _require_completed(job_id, job)

    if not job.get("mom_available"):
        raise HTTPException(status_code=404, detail="MoM not yet available.")

    return JSONResponse(content=job.get("mom", {}))


# ── Chat ──────────────────────────────────────────────────────────────────────

@app.post("/api/v1/jobs/{job_id}/chat", tags=["Chat"])
async def chat(job_id: str, req: ChatRequest):
    """
    Ask a question about the meeting. Uses RAG over the meeting's vector store.
    Returns an answer with timestamp-cited sources.
    """
    job = _get_job_or_404(job_id)
    _require_completed(job_id, job)

    # Load vector store (from memory or disk)
    store = _get_store(job_id)

    if settings.llm_backend == "template":
        # Template fallback: return raw search results as answer
        results = store.search(req.question, top_k=settings.rag_top_k)
        filtered = [r for r in results if r.get("score", 0) >= settings.rag_score_threshold]
        if not filtered:
            return ChatResponse(
                answer="I couldn't find relevant information in the transcript for that question.",
                sources=[]
            )
        answer_parts = []
        for r in filtered:
            answer_parts.append(f"[{r['start_timestamp']}] {r['raw_text'][:200]}")
        return ChatResponse(
            answer="\n\n".join(answer_parts),
            sources=_format_sources(filtered)
        )

    # RAG + LLM answer
    rag = _make_rag(store)

    # Build context-aware prompt including conversation history
    history_text = ""
    if req.history:
        history_text = "\n".join(
            f"{'User' if h['role']=='user' else 'Assistant'}: {h['content']}"
            for h in req.history[-6:]  # last 3 turns
        )

    question = req.question
    if history_text:
        question = f"Conversation so far:\n{history_text}\n\nNew question: {req.question}"

    # Retrieve relevant chunks
    results = store.search(req.question, top_k=settings.rag_top_k)
    filtered = [r for r in results if r.get("score", 0) >= settings.rag_score_threshold]

    if not filtered:
        return ChatResponse(
            answer="I couldn't find relevant information in the transcript for that question.",
            sources=[]
        )

    context = rag._format_context(filtered)

    prompt = f"""Using the meeting transcript excerpts below, answer the following question.
You MUST cite timestamps like [HH:MM:SS] when referencing specific moments.
Be concise and factual. If the answer is not in the excerpts, say so clearly.

Question: {question}

{context}"""

    answer = rag._call_llm_raw(prompt)

    return ChatResponse(
        answer=answer,
        sources=_format_sources(filtered)
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_job_or_404(job_id: str) -> dict:
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return jobs[job_id]


def _require_completed(job_id: str, job: dict):
    if job["status"] == "failed":
        raise HTTPException(status_code=400, detail=f"Job failed: {job.get('error', 'unknown error')}")
    if job["status"] != "completed":
        raise HTTPException(
            status_code=202,
            detail=f"Job is still processing. Status: {job['status']} — {job['step']}"
        )


def _get_store(job_id: str) -> MeetingVectorStore:
    """Load vector store from memory cache or disk."""
    if job_id in vector_stores:
        return vector_stores[job_id]

    store_dir = settings.jobs_dir / job_id / "vector_store"
    if not store_dir.exists():
        raise HTTPException(status_code=404, detail="Vector store not found for this job.")

    store = MeetingVectorStore(model_name=settings.embedding_model)
    store.load(str(store_dir))
    store._get_model()
    vector_stores[job_id] = store
    return store


def _job_summary(job_id: str, job: dict) -> dict:
    return {
        "job_id":       job_id,
        "status":       job["status"],
        "step":         job["step"],
        "progress":     job["progress"],
        "filename":     job["filename"],
        "file_type":    job["file_type"],
        "created_at":   job["created_at"],
        "completed_at": job.get("completed_at"),
        "error":        job.get("error"),
    }


def _job_detail(job_id: str, job: dict) -> dict:
    d = _job_summary(job_id, job)
    d.update({
        "transcript_available": job.get("transcript_available", False),
        "mom_available":        job.get("mom_available", False),
        "chunk_count":          job.get("chunk_count", 0),
        "duration_seconds":     job.get("duration_seconds"),
    })
    return d


def _format_sources(chunks: List[dict]) -> List[dict]:
    return [
        {
            "chunk_id":        c.get("chunk_id"),
            "start_timestamp": c.get("start_timestamp"),
            "end_timestamp":   c.get("end_timestamp"),
            "start":           c.get("start"),
            "end":             c.get("end"),
            "speakers":        c.get("speakers", []),
            "text":            c.get("raw_text", "")[:300],
            "score":           round(c.get("score", 0), 3),
        }
        for c in chunks
    ]
