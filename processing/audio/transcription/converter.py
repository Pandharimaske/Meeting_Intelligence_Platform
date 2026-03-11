"""
audio_to_text/converter.py
──────────────────────────
Transcription via WhisperX (3.8.x) with built-in word-level alignment and
speaker diarization via pyannote.audio 4.x.

WhisperX pipeline (all steps run here):
  1. whisperx.load_model()           - CTranslate2-accelerated Whisper
  2. model.transcribe()              - batched transcription -> segments
  3. whisperx.load_align_model()     - phoneme aligner for the language
  4. whisperx.align()                - word-level timestamps per segment
  5. whisperx.DiarizationPipeline()  - pyannote 4.x speaker diarization
  6. whisperx.assign_word_speakers() - merge diarization -> per-word speaker

pyannote.audio 4.x notes:
  - DiarizationPipeline accepts `use_auth_token` as a kwarg (still works)
  - The internal Inference class no longer accepts use_auth_token — but
    WhisperX 3.8.x calls it correctly through DiarizationPipeline, so
    we just need to NOT pass use_auth_token to whisperx.load_model() VAD.

The returned segment dicts have the same shape as vanilla Whisper so
the rest of the pipeline (chunker, vector store, MoM) is unchanged.
"""

from __future__ import annotations

import json
import asyncio
from pathlib import Path
from typing import Optional

import torch

# Try to import whisperx
try:
    import whisperx
    _WHISPERX_AVAILABLE = True
except ImportError:
    _WHISPERX_AVAILABLE = False
    whisperx = None


# ── Global model cache for 10x faster processing ───────────────────────

_MODEL_CACHE = {}
_CACHE_LOCK = asyncio.Lock() if asyncio else None

def _get_cached_model(model_size: str, device: str, compute_type: str, language: Optional[str] = None) -> any:
    """Get cached WhisperX model or load and cache it."""
    cache_key = f"{model_size}_{device}_{compute_type}_{language or 'auto'}"

    if cache_key in _MODEL_CACHE:
        print(f"  ✓ Using cached WhisperX model: {cache_key}")
        return _MODEL_CACHE[cache_key]

    print(f"  Loading WhisperX model '{model_size}' | device={device} | compute={compute_type}")
    model = whisperx.load_model(
        model_size,
        device=device,
        compute_type=compute_type,
        language=language,
    )

    _MODEL_CACHE[cache_key] = model
    print(f"  ✓ Model cached: {cache_key}")
    return model


# ── Helper: format seconds -> HH:MM:SS ───────────────────────────────────────

def _fmt(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


# ── Main converter class ──────────────────────────────────────────────────────

class AudioToTextConverter:
    """
    Transcribe audio with WhisperX 3.8.x and optionally diarise speakers
    using pyannote.audio 4.x.

    Args:
        model_size:          WhisperX model size
                             (tiny | base | small | medium | large-v2 | large-v3)
        enable_diarization:  Run pyannote speaker diarization.
        huggingface_token:   HuggingFace token — required for diarization.
        compute_type:        CTranslate2 precision (float16 | int8 | float32).
                             Defaults to float16 on CUDA, int8 on CPU.
        batch_size:          Batch size for WhisperX transcription.
        language:            Language hint (e.g. "en"). None = auto-detect.
    """

    def __init__(
        self,
        model_size: str = "base",
        enable_diarization: bool = False,
        huggingface_token: Optional[str] = None,
        compute_type: Optional[str] = None,
        batch_size: int = 16,
        language: Optional[str] = "en",
    ):
        if not _WHISPERX_AVAILABLE:
            raise ImportError(
                "whisperx is not installed. "
                "Run: pip install whisperx  (or uv sync)"
            )

        self.model_size = model_size
        self.enable_diarization = enable_diarization
        self.huggingface_token = huggingface_token
        self.batch_size = batch_size
        self.language = language

        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        # Auto compute type based on device
        if compute_type is None:
            self.compute_type = "float16" if self.device == "cuda" else "int8"
        else:
            self.compute_type = compute_type

        print(f"  Loading WhisperX model '{model_size}' | device={self.device} | compute={self.compute_type}")

        # whisperx.load_model() in 3.8.x — do NOT pass use_auth_token here.
        # The VAD model (pyannote segmentation) is bundled with whisperx and
        # does not need a HF token. Passing use_auth_token triggers the old
        # pyannote Inference path which breaks on pyannote 4.x.
        self.model = _get_cached_model(
            model_size,
            self.device,
            self.compute_type,
            self.language,
        )

    # ── Main entry point ──────────────────────────────────────────────────────

    def convert_audio_to_text(
        self,
        audio_path: str,
        output_dir: str = "data/transcripts",
    ) -> dict:
        """
        Full WhisperX pipeline: transcribe -> align -> (diarise) -> merge.

        Returns a dict compatible with the rest of the platform:
            text             : str  - full plain text
            segments         : list - segment dicts with start/end/text/speaker
            speaker_segments : list - merged speaker-turn dicts
            speakers         : dict - per-speaker stats
            total_speakers   : int
            language         : str
            text_file        : str  - path to saved .txt
            json_file        : str  - path to saved .json
            diarization_enabled : bool
            device_used      : str
            source           : str  - always "whisperx"
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        try:
            # ── Step 1: Load audio & transcribe ──────────────────────────
            print(f"  Transcribing: {audio_path}")
            audio = whisperx.load_audio(str(audio_path))

            result = self.model.transcribe(
                audio,
                batch_size=self.batch_size,
                language=self.language,
            )
            language = result.get("language", self.language or "en")
            print(f"  Transcription done - language: {language}")

            # ── Step 2: Word-level alignment ──────────────────────────────
            print("  Aligning words...")
            try:
                align_model, align_metadata = whisperx.load_align_model(
                    language_code=language,
                    device=self.device,
                )
                result = whisperx.align(
                    result["segments"],
                    align_model,
                    align_metadata,
                    audio,
                    self.device,
                    return_char_alignments=False,
                )
                print("  Alignment done")
            except Exception as e:
                print(f"  Alignment failed ({e}), continuing without word timestamps")

            # ── Step 3: Speaker diarization (pyannote 4.x) ────────────────
            if self.enable_diarization and self.huggingface_token:
                print("  Running speaker diarization...")
                try:
                    # In whisperx 3.8.x + pyannote 4.x, DiarizationPipeline
                    # accepts use_auth_token as a keyword argument correctly.
                    diarize_model = whisperx.DiarizationPipeline(
                        use_auth_token=self.huggingface_token,
                        device=self.device,
                    )
                    diarize_segments = diarize_model(audio)
                    result = whisperx.assign_word_speakers(diarize_segments, result)
                    print("  Diarization complete")
                except Exception as e:
                    print(f"  Diarization failed ({e}), continuing without speakers")
            elif self.enable_diarization and not self.huggingface_token:
                print("  Diarization requested but no HuggingFace token — skipping")

            # ── Step 4: Normalise segments ────────────────────────────────
            segments = self._normalise_segments(result.get("segments", []))

            # ── Step 5: Build speaker-turn list ───────────────────────────
            speaker_segments, speakers = self._build_speaker_segments(segments)

            # ── Step 6: Full text ─────────────────────────────────────────
            full_text = " ".join(s["text"].strip() for s in segments)

            # ── Step 7: Persist ───────────────────────────────────────────
            txt_path = output_path / f"{audio_path.stem}.txt"
            with open(txt_path, "w", encoding="utf-8") as f:
                if speaker_segments:
                    for turn in speaker_segments:
                        ts = _fmt(turn["start"])
                        f.write(f"[{ts}] {turn['speaker']}: {turn['text']}\n\n")
                else:
                    f.write(full_text)

            json_payload = {
                "text": full_text,
                "language": language,
                "segments": segments,
                "speaker_segments": speaker_segments,
                "speakers": speakers,
                "total_speakers": len(speakers),
                "source": "whisperx",
            }
            json_path = output_path / f"{audio_path.stem}.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(json_payload, f, indent=2, default=str)

            print(f"  Saved -> {txt_path}")
            print(f"  Saved -> {json_path}")
            if speakers:
                print(f"  Speakers detected: {len(speakers)}")

            return {
                "text": full_text,
                "text_file": str(txt_path),
                "json_file": str(json_path),
                "language": language,
                "segments": segments,
                "speaker_segments": speaker_segments,
                "speakers": speakers,
                "total_speakers": len(speakers),
                "diarization_enabled": self.enable_diarization,
                "device_used": self.device,
                "source": "whisperx",
            }

        except Exception as e:
            raise RuntimeError(f"WhisperX transcription failed for {audio_path}: {e}") from e

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _normalise_segments(self, raw_segments: list) -> list:
        """
        Normalise WhisperX segment dicts into a consistent shape.

        WhisperX adds 'words' (word-level alignment) and optionally
        'speaker' (from diarization). We ensure start/end/text/speaker
        are always present.
        """
        normalised = []
        for seg in raw_segments:
            # Derive speaker: segment-level first, then most common word speaker
            speaker = seg.get("speaker")
            if not speaker:
                word_speakers = [
                    w.get("speaker") for w in seg.get("words", []) if w.get("speaker")
                ]
                if word_speakers:
                    speaker = max(set(word_speakers), key=word_speakers.count)

            normalised.append({
                "start":   float(seg.get("start", 0)),
                "end":     float(seg.get("end", 0)),
                "text":    seg.get("text", "").strip(),
                "speaker": speaker or "Unknown",
                "words":   seg.get("words", []),
            })
        return normalised

    def _build_speaker_segments(self, segments: list) -> tuple[list, dict]:
        """
        Merge consecutive same-speaker segments into speaker turns.

        Returns:
            speaker_segments : list of {speaker, text, start, end, ...}
            speakers         : dict {label: {total_duration, segment_count}}
        """
        speaker_turns: list = []
        speakers: dict = {}

        current_speaker: Optional[str] = None
        current_text: list[str] = []
        current_start: float = 0.0
        current_end: float = 0.0

        for seg in segments:
            spk = seg.get("speaker", "Unknown")
            if spk != current_speaker:
                if current_text and current_speaker:
                    speaker_turns.append({
                        "speaker":         current_speaker,
                        "text":            " ".join(current_text),
                        "start":           current_start,
                        "end":             current_end,
                        "start_timestamp": _fmt(current_start),
                        "end_timestamp":   _fmt(current_end),
                    })
                    _update_speaker_stats(speakers, current_speaker, current_start, current_end)

                current_speaker = spk
                current_text    = [seg["text"]]
                current_start   = seg["start"]
                current_end     = seg["end"]
            else:
                current_text.append(seg["text"])
                current_end = seg["end"]

        # Flush last turn
        if current_text and current_speaker:
            speaker_turns.append({
                "speaker":         current_speaker,
                "text":            " ".join(current_text),
                "start":           current_start,
                "end":             current_end,
                "start_timestamp": _fmt(current_start),
                "end_timestamp":   _fmt(current_end),
            })
            _update_speaker_stats(speakers, current_speaker, current_start, current_end)

        return speaker_turns, speakers


# ── Speaker stats helper ──────────────────────────────────────────────────────

def _update_speaker_stats(speakers: dict, label: str, start: float, end: float) -> None:
    duration = max(0.0, end - start)
    if label not in speakers:
        speakers[label] = {"total_duration": 0.0, "segment_count": 0}
    speakers[label]["total_duration"] += duration
    speakers[label]["segment_count"]  += 1


# ── Convenience function ──────────────────────────────────────────────────────

def convert_audio_to_text(
    audio_path: str,
    model_size: str = "base",
    output_dir: str = "data/transcripts",
    enable_diarization: bool = False,
    huggingface_token: Optional[str] = None,
    compute_type: Optional[str] = None,
    batch_size: int = 16,
    language: Optional[str] = "en",
) -> dict:
    """
    Convenience wrapper — signature-compatible with old whisper-based version.
    """
    converter = AudioToTextConverter(
        model_size=model_size,
        enable_diarization=enable_diarization,
        huggingface_token=huggingface_token,
        compute_type=compute_type,
        batch_size=batch_size,
        language=language,
    )
    return converter.convert_audio_to_text(audio_path, output_dir=output_dir)
