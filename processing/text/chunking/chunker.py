import json
from pathlib import Path
from typing import List, Dict


class TranscriptChunker:
    """
    Splits a WhisperX transcript into semantic, time-aligned chunks.

    Key design:
    Before embedding, each chunk is prefixed with metadata:
        [Time: 00:01:23 - 00:02:45 | Speakers: Speaker 0, Speaker 1]
        "He said it's too high, so we rejected it."

    This injects context (who, when) into the vector so queries like
    "what did they decide about the budget?" can match chunks that only
    contain pronouns and no explicit keywords.

    Compatible with both plain WhisperX segments and diarized segments
    (where each segment has a 'speaker' field).
    """

    def __init__(self, max_chunk_words: int = 120, overlap_segments: int = 1):
        """
        Args:
            max_chunk_words:   Target max words per chunk. Chunks are split at
                               segment boundaries, so actual size may vary slightly.
            overlap_segments:  Number of segments to repeat at the start of the
                               next chunk for context continuity.
        """
        self.max_chunk_words = max_chunk_words
        self.overlap_segments = overlap_segments

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chunk_transcript(self, transcript_json_path: str) -> List[Dict]:
        """
        Load a WhisperX JSON transcript and return a list of chunks.

        Each chunk dict contains:
            - chunk_id        : int
            - start           : float  (seconds)
            - end             : float  (seconds)
            - start_timestamp : str    "HH:MM:SS"
            - end_timestamp   : str    "HH:MM:SS"
            - speakers        : list   unique speaker labels in this chunk
            - primary_speaker : str    most frequent speaker in this chunk
            - raw_text        : str    plain concatenated text
            - embedded_text   : str    metadata-prefixed text used for embedding
            - segments        : list   original segment dicts

        Args:
            transcript_json_path: Path to the WhisperX JSON file.

        Returns:
            List of chunk dicts.
        """
        path = Path(transcript_json_path)
        if not path.exists():
            raise FileNotFoundError(f"Transcript not found: {path}")

        with open(path) as f:
            data = json.load(f)

        segments = data.get("segments", [])
        if not segments:
            raise ValueError("Transcript contains no segments.")

        print(f"  Chunking {len(segments)} segments (max {self.max_chunk_words} words/chunk)...")
        chunks = self._build_chunks(segments)
        print(f"  ✓ Created {len(chunks)} chunks")
        return chunks

    def chunk_from_segments(self, segments: List[Dict]) -> List[Dict]:
        """
        Build chunks directly from a list of segment dicts (already in memory).
        Used by api.py after WhisperX transcription completes.
        """
        return self._build_chunks(segments)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_chunks(self, segments: List[Dict]) -> List[Dict]:
        chunks = []
        current_segs = []
        current_words = 0
        chunk_id = 0

        for i, seg in enumerate(segments):
            seg_words = len(seg.get("text", "").split())
            current_segs.append(seg)
            current_words += seg_words

            is_last = (i == len(segments) - 1)
            over_limit = current_words >= self.max_chunk_words

            if over_limit or is_last:
                chunk = self._make_chunk(chunk_id, current_segs)
                chunks.append(chunk)
                chunk_id += 1

                # Overlap: carry last N segments into next chunk
                current_segs = current_segs[-self.overlap_segments:] if self.overlap_segments > 0 else []
                current_words = sum(len(s.get("text", "").split()) for s in current_segs)

        return chunks

    def _make_chunk(self, chunk_id: int, segments: List[Dict]) -> Dict:
        start = segments[0]["start"]
        end = segments[-1]["end"]

        raw_text = " ".join(s.get("text", "").strip() for s in segments).strip()

        # Collect unique speakers in order of appearance
        # WhisperX sets 'speaker' per segment after diarization
        speakers = list(dict.fromkeys(
            s["speaker"] for s in segments if s.get("speaker") and s["speaker"] != "Unknown"
        ))
        # Fall back to "Unknown" if no speakers identified
        if not speakers:
            speakers = list(dict.fromkeys(
                s.get("speaker", "Unknown") for s in segments
            ))

        # Primary speaker = most frequent in this chunk
        speaker_counts: Dict[str, int] = {}
        for s in segments:
            sp = s.get("speaker", "Unknown")
            speaker_counts[sp] = speaker_counts.get(sp, 0) + 1
        primary_speaker = max(speaker_counts, key=speaker_counts.get) if speaker_counts else "Unknown"

        # Build the metadata-enriched text for embedding
        embedded_text = self._build_embedded_text(raw_text, start, end, speakers)

        return {
            "chunk_id": chunk_id,
            "start": start,
            "end": end,
            "start_timestamp": self._fmt_time(start),
            "end_timestamp": self._fmt_time(end),
            "speakers": speakers,
            "primary_speaker": primary_speaker,
            "raw_text": raw_text,
            "embedded_text": embedded_text,
            "segments": segments,
            "word_count": len(raw_text.split()),
            "duration": round(end - start, 2),
        }

    def _build_embedded_text(self, text: str, start: float, end: float, speakers: List[str]) -> str:
        """
        Prefix plain text with contextual metadata before embedding.
        e.g.:
            [Time: 00:04:10 - 00:05:30 | Speakers: Speaker 0, Speaker 1]
            He said it's too high, so we rejected it.
        """
        time_part = f"Time: {self._fmt_time(start)} - {self._fmt_time(end)}"
        speaker_part = f"Speakers: {', '.join(speakers)}" if speakers else ""

        meta_parts = [time_part]
        if speaker_part:
            meta_parts.append(speaker_part)

        meta = "[" + " | ".join(meta_parts) + "]"
        return f"{meta}\n{text}"

    @staticmethod
    def _fmt_time(seconds: float) -> str:
        """Convert float seconds to HH:MM:SS string."""
        seconds = int(seconds)
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h:02d}:{m:02d}:{s:02d}"


# ------------------------------------------------------------------
# Convenience function
# ------------------------------------------------------------------

def chunk_transcript(transcript_json_path: str, max_chunk_words: int = 120) -> List[Dict]:
    """
    Convenience function to chunk a WhisperX JSON transcript.

    Args:
        transcript_json_path: Path to WhisperX JSON output file.
        max_chunk_words:      Approx max words per chunk (default 120).

    Returns:
        List of chunk dicts with embedded_text ready for vectorisation.
    """
    chunker = TranscriptChunker(max_chunk_words=max_chunk_words)
    return chunker.chunk_transcript(transcript_json_path)
