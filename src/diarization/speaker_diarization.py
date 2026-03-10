"""
diarization/speaker_diarization.py
───────────────────────────────────
Standalone pyannote-based diarization — kept as a fallback / utility.

Primary diarization is now done inside WhisperX (converter.py) via
whisperx.DiarizationPipeline + whisperx.assign_word_speakers().

This module is retained for:
  • Direct / standalone diarization calls (e.g. for SRT files)
  • Fallback if the WhisperX diarization step fails
  • CLI / notebook usage independent of the full pipeline
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


class SpeakerDiarizer:
    """
    Speaker diarization using pyannote.audio 3.x.

    Args:
        use_auth_token: HuggingFace token for pyannote/speaker-diarization-3.1
    """

    _MODEL_ID = "pyannote/speaker-diarization-3.1"

    def __init__(self, use_auth_token: Optional[str] = None):
        self.use_auth_token = use_auth_token
        self.pipeline = None

    # ── Lazy pipeline loader ──────────────────────────────────────────────────

    def _load_pipeline(self) -> None:
        if self.pipeline is not None:
            return
        try:
            from pyannote.audio import Pipeline
            self.pipeline = Pipeline.from_pretrained(
                self._MODEL_ID,
                use_auth_token=self.use_auth_token,
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to load pyannote pipeline '{self._MODEL_ID}': {e}\n"
                "Make sure you have accepted the model licence on HuggingFace "
                "and provided a valid HUGGINGFACE_TOKEN."
            ) from e

    # ── Public API ────────────────────────────────────────────────────────────

    def diarize(self, audio_path: str) -> dict:
        """
        Run speaker diarization on an audio file.

        Returns:
            {
                segments      : list[{speaker, start, end, duration}]
                speakers      : dict[str, {total_duration, segment_count}]
                total_speakers: int
                total_duration: float
            }
        """
        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")

        self._load_pipeline()

        print(f"  Diarizing: {path}")
        diarization = self.pipeline(str(path))

        speakers: dict = {}
        segments: list = []
        total_duration = 0.0

        for turn, _, raw_label in diarization.itertracks(yield_label=True):
            # pyannote labels: SPEAKER_00, SPEAKER_01 …
            idx = raw_label.split("_")[-1].lstrip("0") or "0"
            speaker_label = f"Speaker {idx}"

            duration = turn.end - turn.start
            total_duration += duration

            segments.append({
                "speaker":  speaker_label,
                "start":    turn.start,
                "end":      turn.end,
                "duration": duration,
            })

            if speaker_label not in speakers:
                speakers[speaker_label] = {"total_duration": 0.0, "segment_count": 0}
            speakers[speaker_label]["total_duration"] += duration
            speakers[speaker_label]["segment_count"]  += 1

        print(f"  ✓ Diarization complete — {len(speakers)} speaker(s) detected")

        return {
            "segments":       segments,
            "speakers":       speakers,
            "total_speakers": len(speakers),
            "total_duration": total_duration,
        }

    def merge_with_transcript(self, transcript: dict, diarization: dict) -> dict:
        """
        Overlap-based merge of a plain Whisper/WhisperX transcript with
        standalone pyannote diarization results.

        Useful when WhisperX diarization is unavailable (no HF token) but
        pyannote has been run separately.

        Mutates and returns an enriched transcript dict.
        """
        segments      = transcript.get("segments", [])
        diar_segments = diarization.get("segments", [])

        for seg in segments:
            seg_start = seg["start"]
            seg_end   = seg["end"]
            best_speaker, max_overlap = "Unknown", 0.0

            for ds in diar_segments:
                overlap = max(0.0, min(seg_end, ds["end"]) - max(seg_start, ds["start"]))
                if overlap > max_overlap:
                    max_overlap  = overlap
                    best_speaker = ds["speaker"]

            seg["speaker"] = best_speaker

        # Rebuild speaker turns
        speaker_turns: list = []
        current_speaker: Optional[str] = None
        current_text:    list[str]     = []
        current_start = current_end = 0.0

        for seg in segments:
            spk = seg.get("speaker", "Unknown")
            if spk != current_speaker:
                if current_text and current_speaker:
                    speaker_turns.append({
                        "speaker": current_speaker,
                        "text":    " ".join(current_text),
                        "start":   current_start,
                        "end":     current_end,
                    })
                current_speaker = spk
                current_text    = [seg["text"]]
                current_start   = seg["start"]
                current_end     = seg["end"]
            else:
                current_text.append(seg["text"])
                current_end = seg["end"]

        if current_text and current_speaker:
            speaker_turns.append({
                "speaker": current_speaker,
                "text":    " ".join(current_text),
                "start":   current_start,
                "end":     current_end,
            })

        transcript.update({
            "segments":        segments,
            "speaker_segments": speaker_turns,
            "speakers":        diarization.get("speakers", {}),
            "total_speakers":  diarization.get("total_speakers", 0),
        })
        return transcript


# ── Convenience function ──────────────────────────────────────────────────────

def perform_diarization(audio_path: str, use_auth_token: Optional[str] = None) -> dict:
    """Convenience wrapper — backwards-compatible with old call sites."""
    return SpeakerDiarizer(use_auth_token=use_auth_token).diarize(audio_path)
