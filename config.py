from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Literal, Optional
from pathlib import Path


class Settings(BaseSettings):
    """
    Central configuration for the Meeting Intelligence Platform.
    Values are loaded from environment variables or a .env file.
    All fields have sensible defaults so the app runs without any .env.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"          # silently ignore unknown env vars
    )

    # ── LLM ───────────────────────────────────────────────────────
    llm_backend: Literal["anthropic", "openai", "openrouter", "template"] = Field(
        default="template",
        description="Which LLM backend to use for MoM generation"
    )
    anthropic_api_key: str = Field(
        default="",
        description="Anthropic API key (sk-ant-...)"
    )
    openai_api_key: str = Field(
        default="",
        description="OpenAI API key (sk-...)"
    )
    openrouter_api_key: str = Field(
        default="",
        description="OpenRouter API key (sk-or-...)"
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter API base URL"
    )
    llm_model: str = Field(
        default="arcee-ai/trinity-large-preview:free",
        description=(
            "Model name. Defaults: "
            "openrouter->arcee-ai/trinity-large-preview:free, "
            "anthropic->claude-haiku-4-5-20251001, "
            "openai->gpt-3.5-turbo"
        )
    )
    llm_max_tokens: int = Field(
        default=2048,
        description="Max tokens for LLM response"
    )
    llm_temperature: float = Field(
        default=0.2,
        description="LLM sampling temperature (lower = more deterministic)"
    )

    # ── WhisperX ──────────────────────────────────────────────────
    whisper_model: Literal["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"] = Field(
        default="base",
        description="WhisperX model size for transcription"
    )
    whisper_language: str = Field(
        default="en",
        description="Language hint for WhisperX (e.g. 'en', 'hi', 'fr')"
    )
    whisperx_compute_type: str = Field(
        default="",
        description=(
            "CTranslate2 compute type: 'float16' (GPU), 'int8' (CPU), 'float32'. "
            "Leave empty to auto-detect based on device."
        )
    )
    whisperx_batch_size: int = Field(
        default=16,
        description="Batch size for WhisperX transcription (reduce if VRAM is limited)"
    )

    # ── Diarization ───────────────────────────────────────────────
    enable_diarization: bool = Field(
        default=False,
        description=(
            "Enable speaker diarization. WhisperX runs pyannote internally "
            "when a huggingface_token is provided."
        )
    )
    huggingface_token: str = Field(
        default="",
        description="HuggingFace token for pyannote diarization models"
    )

    # ── Embeddings ────────────────────────────────────────────────
    embedding_model: str = Field(
        default="all-MiniLM-L6-v2",
        description="SentenceTransformer model for chunk embeddings"
    )

    # ── Chunking ──────────────────────────────────────────────────
    chunk_max_words: int = Field(
        default=120,
        description="Approximate max words per transcript chunk"
    )
    chunk_overlap_segments: int = Field(
        default=1,
        description="Number of segments to overlap between consecutive chunks"
    )

    # ── RAG ───────────────────────────────────────────────────────
    rag_top_k: int = Field(
        default=5,
        description="Number of chunks to retrieve per RAG query"
    )
    rag_score_threshold: float = Field(
        default=0.3,
        description="Minimum cosine similarity score to include a chunk"
    )

    # ── Paths ─────────────────────────────────────────────────────
    data_dir: Path = Field(
        default=Path("data"),
        description="Root directory for all data files"
    )
    audio_dir: Path = Field(
        default=Path("data/audio"),
        description="Directory for extracted audio files"
    )
    transcript_dir: Path = Field(
        default=Path("data/transcripts"),
        description="Directory for transcript files"
    )
    jobs_dir: Path = Field(
        default=Path("data/jobs"),
        description="Directory for job outputs (chunks, vector store, MoM)"
    )
    video_dir: Path = Field(
        default=Path("data/video"),
        description="Directory for uploaded video files"
    )
    clips_dir: Path = Field(
        default=Path("data/clips"),
        description="Directory for generated video clips"
    )

    # ── API Server ────────────────────────────────────────────────
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    api_reload: bool = Field(default=True)
    log_level: Literal["debug", "info", "warning", "error"] = Field(default="info")

    # ── Helpers ───────────────────────────────────────────────────

    def get_llm_model(self) -> str:
        """Return effective model name, applying defaults per backend."""
        if self.llm_model:
            return self.llm_model
        defaults = {
            "anthropic":  "claude-haiku-4-5-20251001",
            "openai":     "gpt-3.5-turbo",
            "openrouter": "arcee-ai/trinity-large-preview:free",
            "template":   ""
        }
        return defaults.get(self.llm_backend, "")

    def get_whisperx_compute_type(self) -> Optional[str]:
        """Return compute_type or None so AudioToTextConverter can auto-detect."""
        return self.whisperx_compute_type if self.whisperx_compute_type else None

    def validate_llm(self) -> None:
        """Raise if the chosen backend has no API key configured."""
        if self.llm_backend == "anthropic" and not self.anthropic_api_key:
            raise ValueError(
                "llm_backend='anthropic' but ANTHROPIC_API_KEY is not set. "
                "Add it to your .env file or set the environment variable."
            )
        if self.llm_backend == "openai" and not self.openai_api_key:
            raise ValueError(
                "llm_backend='openai' but OPENAI_API_KEY is not set. "
                "Add it to your .env file or set the environment variable."
            )
        if self.llm_backend == "openrouter" and not self.openrouter_api_key:
            raise ValueError(
                "llm_backend='openrouter' but OPENROUTER_API_KEY is not set. "
                "Add it to your .env file or set the environment variable."
            )

    def job_dir(self, meeting_name: str) -> Path:
        """Return the job output directory for a given meeting."""
        return self.jobs_dir / meeting_name


# ── Module-level singleton ─────────────────────────────────────────
# Import this everywhere: `from config import settings`
settings = Settings()
