"""
Meeting Intelligence Platform — Full API

Pipeline per upload:
  1. Save file
  2. If video  → extract audio
     If SRT    → parse transcript directly (skip Whisper)
     If audio  → Whisper transcription
  3. Transcript → semantic chunks  (speaker + timestamp preserved)
  4. Chunks → FAISS vector store  (rich metadata for video clipping)
  5. Vector store + RAG → MoM (Minutes of Meeting)
  6. Vector store kept in memory for /chat endpoint

Re-run endpoints (skip the slow transcription step):
  POST /api/v1/jobs/{job_id}/rerun/chunks   → re-chunk from saved transcript
  POST /api/v1/jobs/{job_id}/rerun/index    → re-embed from saved chunks
  POST /api/v1/jobs/{job_id}/rerun/mom      → re-generate MoM from saved index
"""

import uuid
import shutil
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.core.settings import settings
from processing.audio.extractor import extract_audio_from_video
from processing.audio.transcription.converter import convert_audio_to_text
from processing.text.parser import parse_srt
from processing.text.chunking.chunker import TranscriptChunker
from processing.vector.store import MeetingVectorStore
from processing.reports.rag_mom_generator import RAGMoMGenerator
from processing.video.clipper import VideoClipper

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Meeting Intelligence Platform",
    description="Upload a meeting audio/video/transcript → get transcript, MoM, and chat with your meeting.",
    version="1.0.0",
)

# ── WebSocket Manager for Real-Time Updates ───────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, job_id: str):
        await websocket.accept()
        self.active_connections[job_id] = websocket

    def disconnect(self, job_id: str):
        if job_id in self.active_connections:
            del self.active_connections[job_id]

    async def send_progress(self, job_id: str, progress: Dict):
        if job_id in self.active_connections:
            try:
                await self.active_connections[job_id].send_json(progress)
            except Exception:
                # Connection might be closed, remove it
                self.disconnect(job_id)

    async def broadcast(self, message: Dict):
        """Broadcast to all connected clients"""
        for connection in self.active_connections.values():
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Range", "Accept-Ranges", "Content-Length"],
)

# Ensure all data dirs exist
for d in [settings.video_dir, settings.audio_dir, settings.transcript_dir, settings.jobs_dir, settings.clips_dir]:
    Path(d).mkdir(parents=True, exist_ok=True)

# Thread pool for CPU-bound work (Whisper, embeddings)
_executor = ThreadPoolExecutor(max_workers=2)

# Main event loop reference — set on first request so background threads
# can schedule coroutines on it via run_coroutine_threadsafe()
_main_loop = None

# Video clipper
_clipper = VideoClipper(str(settings.clips_dir))

# ── In-memory state ───────────────────────────────────────────────────────────

jobs: Dict[str, dict] = {}
vector_stores: Dict[str, MeetingVectorStore] = {}

# Jobs database file (persistent JSON)
_jobs_db_file = settings.jobs_dir / "jobs.json"

# ── Persistence Layer ──────────────────────────────────────────────────────────

def _save_jobs_to_disk():
    """Persist all jobs to JSON database."""
    try:
        _jobs_db_file.parent.mkdir(parents=True, exist_ok=True)
        with open(_jobs_db_file, 'w') as f:
            json.dump(jobs, f, indent=2, default=str)
    except Exception as e:
        print(f"⚠️  Failed to save jobs database: {e}")

def _load_jobs_from_disk():
    """Load all jobs from JSON database."""
    global jobs
    if _jobs_db_file.exists():
        try:
            with open(_jobs_db_file, 'r') as f:
                jobs = json.load(f)
            print(f"✅ Loaded {len(jobs)} jobs from cache")
        except Exception as e:
            print(f"⚠️  Failed to load jobs database: {e}")
            jobs = {}
    else:
        jobs = {}

def _get_vector_store_path(job_id: str) -> Path:
    """Get the filesystem path for a job's FAISS vector store."""
    return settings.jobs_dir / job_id / "vector_store"

def _save_vector_store(job_id: str, store: MeetingVectorStore):
    """Save vector store to disk using FAISS."""
    try:
        store_path = _get_vector_store_path(job_id)
        store_path.mkdir(parents=True, exist_ok=True)
        store.save(str(store_path))
    except Exception as e:
        print(f"⚠️  Failed to save vector store for {job_id}: {e}")

def _load_vector_store(job_id: str) -> Optional[MeetingVectorStore]:
    """Load vector store from disk using FAISS."""
    try:
        store_path = _get_vector_store_path(job_id)
        if store_path.exists():
            store = MeetingVectorStore(model_name=settings.embedding_model)
            store.load(str(store_path))
            return store
    except Exception as e:
        print(f"⚠️  Failed to load vector store for {job_id}: {e}")
    return None

def _get_store(job_id: str) -> MeetingVectorStore:
    """Get or load vector store for a job."""
    if job_id in vector_stores:
        return vector_stores[job_id]
    
    # Try to load from disk
    store = _load_vector_store(job_id)
    if store:
        vector_stores[job_id] = store
        return store
    
    raise HTTPException(status_code=404, detail=f"Vector store not found for job {job_id}")

# Load existing jobs on startup
_load_jobs_from_disk()

# MIME type map for video extensions
_VIDEO_MIME = {
    ".mp4":  "video/mp4",
    ".mov":  "video/quicktime",
    ".avi":  "video/x-msvideo",
    ".mkv":  "video/x-matroska",
    ".webm": "video/webm",
    ".flv":  "video/x-flv",
    ".wmv":  "video/x-ms-wmv",
}

# ── Pydantic models ───────────────────────────────────────────────────────────

class JobStatus(BaseModel):
    job_id: str
    status: str
    step: str
    progress: int
    filename: str
    file_type: str
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
    history: Optional[List[Dict]] = []

class ChatResponse(BaseModel):
    answer: str
    sources: List[Dict] = []
    wants_clip: bool = False  # Indicates if user asked for video clip


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


# ── Video range-request helper ────────────────────────────────────────────────

def _parse_range_header(range_header: str, file_size: int) -> Tuple[int, int]:
    """Parse 'Range: bytes=start-end' and return (start, end) clamped to file size."""
    try:
        unit, rng = range_header.split("=", 1)
        if unit.strip().lower() != "bytes":
            return 0, file_size - 1
        start_str, _, end_str = rng.partition("-")
        start = int(start_str) if start_str.strip() else 0
        end   = int(end_str)   if end_str.strip()   else file_size - 1
        start = max(0, min(start, file_size - 1))
        end   = max(start, min(end, file_size - 1))
        return start, end
    except Exception:
        return 0, file_size - 1


def _video_streaming_response(video_path: Path, request: Request) -> StreamingResponse:
    """
    Return a StreamingResponse that honours HTTP Range requests.
    Browsers send Range headers for video scrubbing/seeking — without this,
    the video element stalls after the initial buffer runs out.
    """
    file_size = video_path.stat().st_size
    mime_type = _VIDEO_MIME.get(video_path.suffix.lower(), "video/mp4")

    range_header = request.headers.get("range")

    if range_header:
        start, end = _parse_range_header(range_header, file_size)
        chunk_size  = end - start + 1

        def iter_file():
            with open(video_path, "rb") as f:
                f.seek(start)
                remaining = chunk_size
                while remaining > 0:
                    data = f.read(min(65536, remaining))   # 64 KB chunks
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        headers = {
            "Content-Range":  f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges":  "bytes",
            "Content-Length": str(chunk_size),
            "Content-Type":   mime_type,
        }
        return StreamingResponse(iter_file(), status_code=206, headers=headers)

    else:
        # Full file — still stream it so memory stays flat
        def iter_full():
            with open(video_path, "rb") as f:
                while True:
                    data = f.read(65536)
                    if not data:
                        break
                    yield data

        headers = {
            "Accept-Ranges":  "bytes",
            "Content-Length": str(file_size),
            "Content-Type":   mime_type,
        }
        return StreamingResponse(iter_full(), status_code=200, headers=headers)


# ── Error handling helpers ──────────────────────────────────────────────────

def _format_error_message(error: Exception) -> str:
    """Format error messages for better user experience."""
    error_str = str(error)

    # Handle common error types with user-friendly messages
    if "No module named" in error_str:
        return f"Missing dependency: {error_str}. Please install required packages."
    elif "CUDA" in error_str or "GPU" in error_str:
        return f"GPU error: {error_str}. Try using CPU mode or check GPU drivers."
    elif "HuggingFace" in error_str or "token" in error_str.lower():
        return f"Authentication error: {error_str}. Check your HuggingFace token."
    elif "file not found" in error_str.lower():
        return f"File error: {error_str}. Check if the file exists and is accessible."
    elif "permission" in error_str.lower():
        return f"Permission error: {error_str}. Check file permissions."
    elif "memory" in error_str.lower():
        return f"Memory error: {error_str}. Try processing smaller files or use CPU mode."
    elif "timeout" in error_str.lower():
        return f"Timeout error: {error_str}. The operation took too long to complete."
    else:
        # For unknown errors, provide a generic but helpful message
        return f"Processing error: {error_str}. Check logs for details."


# ── Pipeline ──────────────────────────────────────────────────────────────────

def _run_pipeline(job_id: str, file_path: Path, file_type: str) -> None:
    """Full processing pipeline. Runs synchronously in a thread pool."""
    def update(status: str, step: str, progress: int):
        jobs[job_id].update({"status": status, "step": step, "progress": progress})
        _save_jobs_to_disk()  # Auto-save after each status update

        # Send real-time progress update via WebSocket
        # Must schedule on the main event loop — cannot use asyncio.run() from a thread
        # that lives outside the main loop.
        if _main_loop and _main_loop.is_running():
            import asyncio as _asyncio
            _asyncio.run_coroutine_threadsafe(
                manager.send_progress(job_id, {
                    "type": "progress",
                    "job_id": job_id,
                    "status": status,
                    "step": step,
                    "progress": progress,
                    "timestamp": datetime.utcnow().isoformat()
                }),
                _main_loop
            )

    try:
        job_dir = settings.jobs_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        # ── Step 1: Obtain transcript ────────────────────────────────────
        if file_type == "srt":
            update("transcribing", "Parsing SRT transcript…", 20)
            transcript = parse_srt(str(file_path))
            print(f"  ✓ SRT parsed: {transcript['total_speakers']} speakers, "
                  f"{len(transcript['segments'])} segments")

        else:
            if file_type == "video":
                update("transcribing", "Extracting audio from video…", 10)
                audio_path = extract_audio_from_video(
                    str(file_path), output_dir=str(settings.audio_dir)
                )
                jobs[job_id]["video_path"] = str(file_path)
            else:
                audio_path = str(file_path)

            update("transcribing", "Transcribing audio with WhisperX…", 25)
            transcript = convert_audio_to_text(
                audio_path,
                model_size=settings.whisper_model,
                output_dir=str(job_dir / "transcripts"),
                enable_diarization=settings.enable_diarization,
                huggingface_token=settings.huggingface_token or None,
                compute_type=settings.get_whisperx_compute_type(),
                batch_size=settings.whisperx_batch_size,
                language=settings.whisper_language or "en",
            )

        jobs[job_id]["transcript"] = transcript
        jobs[job_id]["transcript_available"] = True

        segments = transcript.get("segments", [])
        if segments:
            jobs[job_id]["duration_seconds"] = segments[-1].get("end", 0)

        # ── Step 2: Chunk ────────────────────────────────────────────────
        update("chunking", "Splitting transcript into semantic chunks…", 45)
        chunker = TranscriptChunker(
            max_chunk_words=settings.chunk_max_words,
            overlap_segments=settings.chunk_overlap_segments,
        )
        chunks = chunker.chunk_from_segments(segments)
        jobs[job_id]["chunk_count"] = len(chunks)

        with open(job_dir / "chunks.json", "w") as f:
            json.dump(chunks, f, indent=2, default=str)

        print(f"  ✓ {len(chunks)} chunks created")

        # ── Step 2.5: Resolve real speaker names via LLM ─────────────────
        if settings.llm_backend != "template" and segments:
            try:
                update("chunking", "Resolving speaker names with AI…", 50)
                from processing.reports.rag_mom_generator import extract_speaker_names_from_segments
                api_key_map = {
                    "openrouter": settings.openrouter_api_key,
                    "anthropic":  settings.anthropic_api_key,
                    "openai":     settings.openai_api_key,
                }
                speaker_names = extract_speaker_names_from_segments(
                    segments,
                    backend=settings.llm_backend,
                    api_key=api_key_map.get(settings.llm_backend, ""),
                    model=settings.get_llm_model(),
                    base_url=settings.openrouter_base_url if settings.llm_backend == "openrouter" else None,
                )
                if speaker_names:
                    jobs[job_id]["speaker_names"] = speaker_names
                    # Remap speaker labels in segments
                    for seg in segments:
                        orig = seg.get("speaker", "")
                        if orig in speaker_names:
                            seg["speaker"] = speaker_names[orig]
                    # Propagate into transcript stored in job
                    if jobs[job_id].get("transcript"):
                        jobs[job_id]["transcript"]["segments"] = segments
                    # Re-chunk with resolved names so embeddings include real names
                    chunks = chunker.chunk_from_segments(segments)
                    jobs[job_id]["chunk_count"] = len(chunks)
                    with open(job_dir / "chunks.json", "w") as f:
                        json.dump(chunks, f, indent=2, default=str)
                    print(f"  ✓ Speaker names resolved: {speaker_names}")
            except Exception as e:
                print(f"  ⚠ Speaker name resolution failed (non-fatal): {e}")

        # ── Step 3: Embed + store ────────────────────────────────────────
        update("indexing", "Embedding chunks and building FAISS index…", 62)
        store = MeetingVectorStore(model_name=settings.embedding_model)
        store.build(chunks, meeting_id=job_id)
        store.save(str(job_dir / "vector_store"), meeting_id=job_id)
        vector_stores[job_id] = store
        _save_vector_store(job_id, store)  # Persist vector store to disk

        # ── Step 4: Generate MoM ─────────────────────────────────────────
        update("generating_mom", "Generating Minutes of Meeting…", 80)
        mom_path = str(job_dir / "mom.json")

        if settings.llm_backend == "template":
            from processing.reports.mom_generator import MoMGenerator
            gen = MoMGenerator(backend="template")
            mom = gen.generate(chunks, output_path=mom_path)
        else:
            rag = _make_rag(store)
            mom = rag.generate(output_path=mom_path)

        jobs[job_id]["mom"] = mom
        jobs[job_id]["mom_available"] = True

        jobs[job_id].update({
            "status":       "completed",
            "step":         "Done",
            "progress":     100,
            "completed_at": datetime.utcnow().isoformat(),
        })
        _save_jobs_to_disk()  # Save final state
        print(f"  ✓ Pipeline complete for job {job_id}")

    except Exception as e:
        error_msg = _format_error_message(e)
        jobs[job_id].update({
            "status": "failed",
            "step":   f"Failed: {error_msg}",
            "progress": 0,
            "error":  error_msg,
            "failed_at": datetime.utcnow().isoformat(),
        })
        _save_jobs_to_disk()

        # Send error update via WebSocket
        if _main_loop and _main_loop.is_running():
            import asyncio as _asyncio
            _asyncio.run_coroutine_threadsafe(
                manager.send_progress(job_id, {
                    "type": "error",
                    "job_id": job_id,
                    "status": "failed",
                    "error": error_msg,
                    "timestamp": datetime.utcnow().isoformat()
                }),
                _main_loop
            )

        print(f"  ❌ Pipeline failed for job {job_id}: {error_msg}")
        raise


# ── Re-run helpers (checkpoint-based) ────────────────────────────────────────

def _rerun_from_chunks(job_id: str) -> None:
    """
    Re-run Step 2 onwards (chunk → embed → MoM) using the saved transcript.
    Skips the slow Whisper transcription entirely.
    Called when: chunking logic changed, chunk_max_words tuned, etc.
    """
    def update(status: str, step: str, progress: int):
        jobs[job_id].update({"status": status, "step": step, "progress": progress})
        _save_jobs_to_disk()

    job_dir = settings.jobs_dir / job_id

    try:
        # Reload transcript from memory (already persisted in jobs.json)
        transcript = jobs[job_id].get("transcript")
        if not transcript:
            raise RuntimeError("No saved transcript found. Cannot re-chunk without a transcript.")

        segments = transcript.get("segments", [])
        if not segments:
            raise RuntimeError("Transcript has no segments.")

        update("chunking", "♻️  Re-chunking from saved transcript…", 40)
        chunker = TranscriptChunker(
            max_chunk_words=settings.chunk_max_words,
            overlap_segments=settings.chunk_overlap_segments,
        )
        chunks = chunker.chunk_from_segments(segments)
        jobs[job_id]["chunk_count"] = len(chunks)

        with open(job_dir / "chunks.json", "w") as f:
            json.dump(chunks, f, indent=2, default=str)

        print(f"  ✓ Re-chunked: {len(chunks)} chunks")

        update("indexing", "♻️  Re-embedding chunks into FAISS…", 65)
        store = MeetingVectorStore(model_name=settings.embedding_model)
        store.build(chunks, meeting_id=job_id)
        store.save(str(job_dir / "vector_store"), meeting_id=job_id)
        vector_stores[job_id] = store

        update("generating_mom", "♻️  Re-generating MoM…", 85)
        mom_path = str(job_dir / "mom.json")

        if settings.llm_backend == "template":
            from processing.reports.mom_generator import MoMGenerator
            gen = MoMGenerator(backend="template")
            mom = gen.generate(chunks, output_path=mom_path)
        else:
            rag = _make_rag(store)
            mom = rag.generate(output_path=mom_path)

        jobs[job_id]["mom"] = mom
        jobs[job_id]["mom_available"] = True
        jobs[job_id].update({
            "status": "completed", "step": "Done", "progress": 100,
            "completed_at": datetime.utcnow().isoformat(),
        })
        _save_jobs_to_disk()
        print(f"  ✓ Re-run (from chunks) complete for job {job_id}")

    except Exception as e:
        jobs[job_id].update({"status": "failed", "step": f"Re-run failed: {e}", "progress": 0, "error": str(e)})
        _save_jobs_to_disk()
        raise


def _rerun_from_index(job_id: str) -> None:
    """
    Re-run Step 3 onwards (embed → MoM) using the saved chunks.json.
    Skips transcription AND chunking.
    Called when: embedding model changed, RAG score_threshold tuned, etc.
    """
    def update(status: str, step: str, progress: int):
        jobs[job_id].update({"status": status, "step": step, "progress": progress})
        _save_jobs_to_disk()

    job_dir = settings.jobs_dir / job_id
    chunks_file = job_dir / "chunks.json"

    try:
        if not chunks_file.exists():
            raise RuntimeError("No chunks.json found. Run re-chunk first.")

        with open(chunks_file) as f:
            chunks = json.load(f)

        update("indexing", "♻️  Re-embedding saved chunks into FAISS…", 60)
        store = MeetingVectorStore(model_name=settings.embedding_model)
        store.build(chunks, meeting_id=job_id)
        store.save(str(job_dir / "vector_store"), meeting_id=job_id)
        vector_stores[job_id] = store

        update("generating_mom", "♻️  Re-generating MoM from new index…", 85)
        mom_path = str(job_dir / "mom.json")

        if settings.llm_backend == "template":
            from processing.reports.mom_generator import MoMGenerator
            gen = MoMGenerator(backend="template")
            mom = gen.generate(chunks, output_path=mom_path)
        else:
            rag = _make_rag(store)
            mom = rag.generate(output_path=mom_path)

        jobs[job_id]["mom"] = mom
        jobs[job_id]["mom_available"] = True
        jobs[job_id].update({
            "status": "completed", "step": "Done", "progress": 100,
            "completed_at": datetime.utcnow().isoformat(),
        })
        _save_jobs_to_disk()
        print(f"  ✓ Re-run (from index) complete for job {job_id}")

    except Exception as e:
        jobs[job_id].update({"status": "failed", "step": f"Re-run failed: {e}", "progress": 0, "error": str(e)})
        _save_jobs_to_disk()
        raise


def _rerun_mom_only(job_id: str) -> None:
    """
    Re-run Step 4 only (MoM generation) using the existing FAISS index.
    The fastest re-run — skips transcription, chunking, AND embedding.
    Called when: MoM prompts changed, LLM backend switched, temperature tuned, etc.
    """
    def update(status: str, step: str, progress: int):
        jobs[job_id].update({"status": status, "step": step, "progress": progress})
        _save_jobs_to_disk()

    job_dir = settings.jobs_dir / job_id

    try:
        update("generating_mom", "♻️  Re-generating MoM from saved index…", 75)

        store = _get_store(job_id)  # loads from disk if not in memory
        mom_path = str(job_dir / "mom.json")

        if settings.llm_backend == "template":
            chunks_file = job_dir / "chunks.json"
            if not chunks_file.exists():
                raise RuntimeError("No chunks.json found.")
            with open(chunks_file) as f:
                chunks = json.load(f)
            from processing.reports.mom_generator import MoMGenerator
            gen = MoMGenerator(backend="template")
            mom = gen.generate(chunks, output_path=mom_path)
        else:
            rag = _make_rag(store)
            mom = rag.generate(output_path=mom_path)

        jobs[job_id]["mom"] = mom
        jobs[job_id]["mom_available"] = True
        jobs[job_id].update({
            "status": "completed", "step": "Done", "progress": 100,
            "completed_at": datetime.utcnow().isoformat(),
        })
        _save_jobs_to_disk()
        print(f"  ✓ Re-run (MoM only) complete for job {job_id}")

    except Exception as e:
        jobs[job_id].update({"status": "failed", "step": f"Re-run failed: {e}", "progress": 0, "error": str(e)})
        _save_jobs_to_disk()
        raise


# ── Routes ────────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def _capture_event_loop():
    """Capture the main asyncio event loop so background threads can use it."""
    global _main_loop
    import asyncio
    _main_loop = asyncio.get_event_loop()


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.get("/", tags=["Health"])
async def root():
    # Let React handle the root route
    react_index = Path(__file__).parent.parent / "frontend" / "build" / "index.html"
    if react_index.exists():
        from fastapi.responses import FileResponse
        return FileResponse(react_index, media_type="text/html")

    # Fallback for development
    return {"name": "Meeting Intelligence Platform", "version": "1.0.0", "docs": "/docs"}


# ── WebSocket for Real-Time Updates ───────────────────────────────────────────

@app.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    await manager.connect(websocket, job_id)
    try:
        while True:
            # Keep connection alive and wait for client messages
            data = await websocket.receive_text()
            # Echo back for connection health
            await websocket.send_json({"type": "ping", "data": data})
    except WebSocketDisconnect:
        manager.disconnect(job_id)


# ── Upload ────────────────────────────────────────────────────────────────────

AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".flv", ".wmv", ".webm"}
SRT_EXTENSIONS   = {".srt", ".vtt"}

@app.post("/api/v1/upload", tags=["Pipeline"])
async def upload_file(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")

    ext = Path(file.filename).suffix.lower()

    if ext in AUDIO_EXTENSIONS:
        file_type, save_dir = "audio", settings.audio_dir
    elif ext in VIDEO_EXTENSIONS:
        file_type, save_dir = "video", settings.video_dir
    elif ext in SRT_EXTENSIONS:
        file_type, save_dir = "srt", settings.transcript_dir
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{ext}'.")

    job_id    = str(uuid.uuid4())
    save_path = Path(save_dir) / f"{job_id}{ext}"

    with open(save_path, "wb") as buf:
        shutil.copyfileobj(file.file, buf)

    jobs[job_id] = {
        "job_id": job_id, "status": "uploaded",
        "step": "Queued for processing…", "progress": 5,
        "filename": file.filename, "file_type": file_type,
        "created_at": datetime.utcnow().isoformat(), "completed_at": None,
        "error": None, "transcript": None, "mom": None,
        "transcript_available": False, "mom_available": False,
        "chunk_count": 0, "duration_seconds": None, "video_path": None,
    }

    loop = asyncio.get_event_loop()
    background_tasks.add_task(
        loop.run_in_executor, _executor, _run_pipeline, job_id, save_path, file_type
    )

    return {"job_id": job_id, "status": "uploaded", "filename": file.filename,
            "file_type": file_type, "message": "Processing started."}


# ── Jobs ──────────────────────────────────────────────────────────────────────

@app.get("/api/v1/jobs", tags=["Jobs"])
async def list_jobs(status: Optional[str] = None):
    result = [_job_summary(jid, job) for jid, job in jobs.items()
              if status is None or job["status"] == status]
    return {"jobs": sorted(result, key=lambda j: j["created_at"], reverse=True), "total": len(result)}


@app.get("/api/v1/jobs/{job_id}", tags=["Jobs"])
async def get_job(job_id: str):
    return _job_detail(job_id, _get_job_or_404(job_id))


# ── Re-run Endpoints (checkpoint-based, skip transcription) ──────────────────

@app.post("/api/v1/jobs/{job_id}/rerun/chunks", tags=["Re-run"])
async def rerun_from_chunks(job_id: str, background_tasks: BackgroundTasks):
    """
    Re-run from Step 2: re-chunk → re-embed → re-generate MoM.

    Use this when you change:
    - Chunking logic (TranscriptChunker)
    - chunk_max_words or chunk_overlap_segments in config
    - Embedding model
    - MoM prompts or LLM backend

    ✅ Skips: Whisper transcription (the slow part)
    ⏱️  Typical time saved: 90-95% vs full re-upload
    """
    job = _get_job_or_404(job_id)
    if not job.get("transcript_available"):
        raise HTTPException(
            status_code=400,
            detail="No transcript found for this job. Cannot re-run without a saved transcript."
        )

    jobs[job_id].update({
        "status": "chunking", "step": "♻️  Re-running from chunks…",
        "progress": 35, "error": None,
    })
    _save_jobs_to_disk()

    loop = asyncio.get_event_loop()
    background_tasks.add_task(loop.run_in_executor, _executor, _rerun_from_chunks, job_id)

    return {
        "job_id": job_id,
        "message": "Re-run started from chunking step. Transcription skipped.",
        "skipped": ["transcription"],
        "running":  ["chunking", "indexing", "mom_generation"],
    }


@app.post("/api/v1/jobs/{job_id}/rerun/index", tags=["Re-run"])
async def rerun_from_index(job_id: str, background_tasks: BackgroundTasks):
    """
    Re-run from Step 3: re-embed saved chunks → re-generate MoM.

    Use this when you change:
    - Embedding model (embedding_model in config)
    - RAG score_threshold or top_k
    - MoM prompts or LLM backend

    ✅ Skips: Whisper transcription + chunking
    ⏱️  Typical time saved: 95%+ vs full re-upload
    """
    job = _get_job_or_404(job_id)
    chunks_file = settings.jobs_dir / job_id / "chunks.json"

    if not chunks_file.exists():
        raise HTTPException(
            status_code=400,
            detail="No chunks.json found. Run /rerun/chunks first."
        )

    jobs[job_id].update({
        "status": "indexing", "step": "♻️  Re-running from embedding step…",
        "progress": 55, "error": None,
    })
    _save_jobs_to_disk()

    loop = asyncio.get_event_loop()
    background_tasks.add_task(loop.run_in_executor, _executor, _rerun_from_index, job_id)

    return {
        "job_id": job_id,
        "message": "Re-run started from embedding step. Transcription + chunking skipped.",
        "skipped": ["transcription", "chunking"],
        "running":  ["indexing", "mom_generation"],
    }


@app.post("/api/v1/jobs/{job_id}/rerun/mom", tags=["Re-run"])
async def rerun_mom_only(job_id: str, background_tasks: BackgroundTasks):
    """
    Re-run Step 4 only: re-generate MoM from the existing FAISS index.

    Use this when you change:
    - MoM system prompt or section prompts (rag_mom_generator.py)
    - LLM backend or model (llm_backend, llm_model in config)
    - LLM temperature or max_tokens
    - RAG score_threshold or top_k

    ✅ Skips: Transcription + chunking + embedding (everything except LLM call)
    ⏱️  Fastest re-run — usually completes in under 60 seconds
    """
    job = _get_job_or_404(job_id)
    store_path = _get_vector_store_path(job_id)

    if not store_path.exists():
        raise HTTPException(
            status_code=400,
            detail="No FAISS index found. Run /rerun/index or /rerun/chunks first."
        )

    jobs[job_id].update({
        "status": "generating_mom", "step": "♻️  Re-generating MoM only…",
        "progress": 70, "error": None,
    })
    _save_jobs_to_disk()

    loop = asyncio.get_event_loop()
    background_tasks.add_task(loop.run_in_executor, _executor, _rerun_mom_only, job_id)

    return {
        "job_id": job_id,
        "message": "MoM re-generation started. All other steps skipped.",
        "skipped": ["transcription", "chunking", "indexing"],
        "running":  ["mom_generation"],
    }


# ── Transcript ────────────────────────────────────────────────────────────────

@app.get("/api/v1/jobs/{job_id}/transcript", tags=["Transcript"])
async def get_transcript(job_id: str, fmt: str = "json"):
    job = _get_job_or_404(job_id)
    _require_completed(job_id, job)
    if not job.get("transcript_available"):
        raise HTTPException(status_code=404, detail="Transcript not yet available.")
    t = job.get("transcript", {})
    if fmt == "txt":
        return JSONResponse(content={"text": t.get("text", "")})
    return JSONResponse(content={
        "text": t.get("text", ""), "language": t.get("language", "en"),
        "segments": t.get("segments", []), "speaker_segments": t.get("speaker_segments", []),
        "speakers": t.get("speakers", {}), "total_speakers": t.get("total_speakers", 0),
        "source": t.get("source", "whisper"),
    })


# ── Video — with HTTP range request support ───────────────────────────────────

@app.get("/api/v1/jobs/{job_id}/video", tags=["Video"])
async def get_video(job_id: str, request: Request):
    """
    Stream the source video with proper HTTP 206 range-request support.
    Browsers require range requests to seek/scrub video — without this,
    the video element shows a black frame even though audio plays fine.
    """
    job = _get_job_or_404(job_id)
    video_path_str = job.get("video_path")
    if not video_path_str:
        raise HTTPException(status_code=404, detail="No video file for this job.")

    video_path = Path(video_path_str)
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video file not found on disk.")

    return _video_streaming_response(video_path, request)


# ── Chunks ────────────────────────────────────────────────────────────────────

@app.get("/api/v1/jobs/{job_id}/chunks", tags=["Chunks"])
async def get_chunks(job_id: str, speaker: Optional[str] = None,
                     start_after: Optional[float] = None, end_before: Optional[float] = None):
    job = _get_job_or_404(job_id)
    _require_completed(job_id, job)
    store  = _get_store(job_id)
    chunks = store._chunks
    if speaker:
        chunks = [c for c in chunks if speaker in c.get("speakers", []) or c.get("primary_speaker") == speaker]
    if start_after is not None:
        chunks = [c for c in chunks if c["start"] >= start_after]
    if end_before is not None:
        chunks = [c for c in chunks if c["end"] <= end_before]
    return {
        "job_id": job_id, "total_chunks": len(chunks),
        "chunks": [{
            "chunk_id": c["chunk_id"], "start": c["start"], "end": c["end"],
            "start_timestamp": c["start_timestamp"], "end_timestamp": c["end_timestamp"],
            "speakers": c["speakers"], "primary_speaker": c.get("primary_speaker", "Unknown"),
            "word_count": c.get("word_count", 0), "duration": c.get("duration", 0.0),
            "raw_text": c["raw_text"],
            "clip_url": f"/api/v1/jobs/{job_id}/clips/{c['start']}/{c['end']}",
        } for c in chunks],
    }


# ── MoM ───────────────────────────────────────────────────────────────────────

@app.get("/api/v1/jobs/{job_id}/mom", tags=["MoM"])
async def get_mom(job_id: str):
    job = _get_job_or_404(job_id)
    _require_completed(job_id, job)
    if not job.get("mom_available"):
        raise HTTPException(status_code=404, detail="MoM not yet available.")
    return JSONResponse(content=job.get("mom", {}))


# ── Chat ──────────────────────────────────────────────────────────────────────

@app.post("/api/v1/jobs/{job_id}/chat/stream", tags=["Chat"])
async def chat_stream(job_id: str, req: ChatRequest):
    """
    Server-Sent Events streaming chat endpoint.
    Yields events: token | sources | clips | followups | done | error
    """
    job = _get_job_or_404(job_id)
    _require_completed(job_id, job)
    store = _get_store(job_id)

    if settings.llm_backend == "template":
        # Fallback: return single non-streaming response as SSE
        results  = store.search(req.question, top_k=settings.rag_top_k)
        filtered = [r for r in results if r.get("score", 0) >= settings.rag_score_threshold]
        answer   = "\n\n".join(f"[{r['start_timestamp']}] {r['raw_text'][:200]}" for r in filtered) \
                   or "I couldn't find relevant information."
        def _template_gen():
            yield f"data: {json.dumps({'type': 'token', 'token': answer})}\n\n"
            if filtered:
                yield f"data: {json.dumps({'type': 'sources', 'sources': _format_sources(job_id, filtered)})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return StreamingResponse(_template_gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    rag = _make_rag(store)
    import queue as _queue

    async def _async_gen():
        q: _queue.Queue = _queue.Queue()
        loop = asyncio.get_event_loop()

        def _run():
            try:
                for ev_type, data in rag.stream_events(req.question, history=req.history or []):
                    q.put((ev_type, data))
            except Exception as exc:
                q.put(("error", str(exc)))
            finally:
                q.put(None)  # sentinel

        future = loop.run_in_executor(_executor, _run)

        while True:
            try:
                item = await loop.run_in_executor(None, lambda: q.get(timeout=60))
            except Exception:
                yield f"data: {json.dumps({'type': 'error', 'error': 'Timeout waiting for LLM'})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                break

            if item is None:
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                break

            ev_type, data = item
            if ev_type == "token":
                yield f"data: {json.dumps({'type': 'token', 'token': data})}\n\n"
            elif ev_type == "sources":
                yield f"data: {json.dumps({'type': 'sources', 'sources': _format_sources(job_id, data)})}\n\n"
            elif ev_type == "clips":
                yield f"data: {json.dumps({'type': 'clips', 'clips': _format_sources(job_id, data)})}\n\n"
            elif ev_type == "followups":
                yield f"data: {json.dumps({'type': 'followups', 'followups': data})}\n\n"
            elif ev_type == "error":
                yield f"data: {json.dumps({'type': 'error', 'error': data})}\n\n"

        await future

    return StreamingResponse(
        _async_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/v1/jobs/{job_id}/chat", tags=["Chat"])
async def chat(job_id: str, req: ChatRequest):
    job = _get_job_or_404(job_id)
    _require_completed(job_id, job)
    store = _get_store(job_id)

    if settings.llm_backend == "template":
        results  = store.search(req.question, top_k=settings.rag_top_k)
        filtered = [r for r in results if r.get("score", 0) >= settings.rag_score_threshold]
        if not filtered:
            return ChatResponse(answer="I couldn't find relevant information.", sources=[], wants_clip=False)
        answer = "\n\n".join(f"[{r['start_timestamp']}] {r['raw_text'][:200]}" for r in filtered)
        return ChatResponse(answer=answer, sources=_format_sources(job_id, filtered), wants_clip=False)

    rag = _make_rag(store)

    # answer_question returns (answer, wants_clip)
    answer, wants_clip = rag.answer_question(req.question, history=req.history or [])

    if wants_clip:
        # Use the smart hybrid clip-search from the RAG generator directly.
        # This gives entity-boosted, deduplicated, top-3 results.
        clip_chunks = rag._find_clip_sources(req.question, top_n=3)
        return ChatResponse(
            answer=answer,
            sources=_format_sources(job_id, clip_chunks),
            wants_clip=True,
        )

    # Normal chat: fetch sources by semantic search
    results  = store.search(req.question, top_k=settings.rag_top_k)
    filtered = [r for r in results if r.get("score", 0) >= settings.rag_score_threshold]
    if not filtered and store._chunks:
        filtered = store._chunks[:min(3, len(store._chunks))]

    return ChatResponse(answer=answer, sources=_format_sources(job_id, filtered), wants_clip=False)


# ── Video Clips ───────────────────────────────────────────────────────────────

@app.get("/api/v1/jobs/{job_id}/clips/{start_time}/{end_time}", tags=["Clips"])
async def get_video_clip(job_id: str, start_time: float, end_time: float):
    try:
        job = _get_job_or_404(job_id)
        video_filename = job.get("filename")
        if not video_filename:
            raise HTTPException(status_code=404, detail="Video filename not found in job metadata.")
        
        expected_ext = Path(video_filename).suffix
        video_path = settings.video_dir / f"{job_id}{expected_ext}"
        
        print(f"\n🎬 CLIP REQUEST:")
        print(f"  Job: {job_id}")
        print(f"  Original filename: {video_filename}")
        print(f"  Expected extension: {expected_ext}")
        print(f"  Video path: {video_path}")
        print(f"  Video exists: {video_path.exists()}")
        print(f"  Time range: {start_time}s - {end_time}s")
        
        if not video_path.exists():
            raise HTTPException(status_code=404, detail=f"Video file not found on disk at {video_path}")
        
        clip_path = _clipper.clip_video(str(video_path), start_time=start_time, end_time=end_time, job_id=job_id)
        if not clip_path:
            raise HTTPException(status_code=500, detail="FFmpeg failed to generate clip. Check server logs for details.")
        
        clip_url = _clipper.get_clip_url(clip_path)
        print(f"✅ Clip URL: {clip_url}")
        return {"clip_url": clip_url, "start_time": start_time, "end_time": end_time}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ CLIP ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Clip generation error: {str(e)}")


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_job_or_404(job_id: str) -> dict:
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return jobs[job_id]

def _require_completed(job_id: str, job: dict):
    if job["status"] == "failed":
        raise HTTPException(status_code=400, detail=f"Job failed: {job.get('error', 'unknown')}")
    if job["status"] != "completed":
        raise HTTPException(status_code=202, detail=f"Still processing: {job['step']}")


def _job_summary(job_id: str, job: dict) -> dict:
    return {
        "job_id": job_id, "status": job["status"], "step": job["step"],
        "progress": job["progress"], "filename": job["filename"],
        "file_type": job["file_type"], "created_at": job["created_at"],
        "completed_at": job.get("completed_at"), "error": job.get("error"),
    }

def _job_detail(job_id: str, job: dict) -> dict:
    d = _job_summary(job_id, job)
    d.update({
        "id": job_id,
        "transcript_available": job.get("transcript_available", False),
        "mom_available":        job.get("mom_available", False),
        "chunk_count":          job.get("chunk_count", 0),
        "duration_seconds":     job.get("duration_seconds"),
        "transcript":           job.get("transcript", {}),
        "mom":                  job.get("mom", {}),
        "source_video":         f"/api/v1/jobs/{job_id}/video" if job.get("video_path") else None,
    })
    return d

def _format_sources(job_id: str, chunks: List[dict]) -> List[dict]:
    return [{
        "chunk_id": c.get("chunk_id"), "start_timestamp": c.get("start_timestamp"),
        "end_timestamp": c.get("end_timestamp"), "start": c.get("start"), "end": c.get("end"),
        "speakers": c.get("speakers", []), "primary_speaker": c.get("primary_speaker", "Unknown"),
        "text": c.get("raw_text", "")[:300], "score": round(c.get("score", 0), 3),
        "clip_url": f"/api/v1/jobs/{job_id}/clips/{c.get('start', 0)}/{c.get('end', 0)}",
    } for c in chunks]

# ── Mount Static Files for React (AFTER all API routes) ─────────────────────────
# These must be mounted LAST so API routes are checked first

# Mount clips directory
clips_path = settings.clips_dir
clips_path.mkdir(parents=True, exist_ok=True)
app.mount("/clips", StaticFiles(directory=str(clips_path)), name="clips")

# Mount static assets
static_path = Path(__file__).parent.parent / "frontend" / "build" / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Mount React app root (catch-all must be last)
react_path = Path(__file__).parent.parent / "frontend" / "build"
if react_path.exists():
    app.mount("/", StaticFiles(directory=str(react_path), html=True), name="react")
