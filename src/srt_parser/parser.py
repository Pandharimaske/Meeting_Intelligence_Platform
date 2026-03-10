"""
SRT / pre-transcribed subtitle file parser.

Converts .srt (or .vtt) transcript files into the same segment format
that Whisper produces, so they can flow directly into TranscriptChunker
without any changes downstream.

Supported transcript formats
─────────────────────────────
Format A — Speaker-labelled (common in Zoom/Meet exports):

    1
    00:00:01,000 --> 00:00:05,000
    John: Hello everyone, let's get started.

Format B — Plain subtitles (no speaker prefix):

    1
    00:00:01,000 --> 00:00:05,000
    Hello everyone, let's get started.

Output segment dict (matches Whisper output):
    {
        "id":      int,
        "start":   float,    # seconds
        "end":     float,    # seconds
        "text":    str,      # clean transcript text (speaker prefix stripped)
        "speaker": str,      # "John" | "Unknown"
    }
"""

import re
from pathlib import Path
from typing import Dict, List, Optional


class SRTParser:
    """Parse SRT/VTT subtitle files into Whisper-compatible segment dicts."""

    # Matches SRT timestamp: 00:00:01,000 --> 00:00:05,000
    # Also handles VTT format with '.' instead of ','
    _TS_RE = re.compile(
        r"(\d{2}):(\d{2}):(\d{2})[,.](\d{1,3})"
        r"\s*-->\s*"
        r"(\d{2}):(\d{2}):(\d{2})[,.](\d{1,3})"
    )

    # Matches "Speaker Name: text" — speaker names start with capital, max 4 words
    _SPEAKER_RE = re.compile(r"^([A-Z][A-Za-z0-9 _\-\.]{0,39}):\s+(.+)$")

    # VTT meta block pattern (skip these)
    _VTT_META_RE = re.compile(r"^(WEBVTT|NOTE|STYLE|REGION)")

    def parse(self, path: str) -> List[Dict]:
        """
        Parse an SRT or VTT file into Whisper-style segment dicts.

        Args:
            path: Path to the .srt / .vtt file.

        Returns:
            List of segment dicts: {id, start, end, text, speaker}
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Transcript file not found: {p}")

        raw = p.read_text(encoding="utf-8", errors="replace")
        raw = raw.replace("\r\n", "\n").replace("\r", "\n")

        blocks = self._split_blocks(raw)
        segments = []
        for block in blocks:
            seg = self._parse_block(block)
            if seg:
                segments.append(seg)

        if not segments:
            raise ValueError(f"No valid subtitle segments found in: {path}")

        # Re-index sequentially (SRT indices can have gaps/duplicates)
        for i, seg in enumerate(segments):
            seg["id"] = i

        print(f"  Parsed {len(segments)} segments from '{p.name}'")
        return segments

    def parse_to_transcript_dict(self, path: str) -> Dict:
        """
        Parse SRT/VTT and return a dict matching Whisper convert_audio_to_text() output.

        Compatible with all downstream components (TranscriptChunker, api.py pipeline).
        """
        segments = self.parse(path)

        full_text = " ".join(s["text"] for s in segments)
        speaker_segments = self._build_speaker_segments(segments)
        speakers = self._build_speaker_stats(segments)
        named_speakers = [s for s in speakers if s != "Unknown"]

        return {
            "text":               full_text,
            "language":           "en",
            "segments":           segments,
            "speaker_segments":   speaker_segments,
            "speakers":           speakers,
            "total_speakers":     len(named_speakers) if named_speakers else len(speakers),
            "source":             "srt",
            # Stub keys expected by api.py
            "text_file":          path,
            "json_file":          path,
            "device_used":        "n/a",
            "diarization_enabled": bool(named_speakers),
        }

    # ── Internal helpers ──────────────────────────────────────────────────

    def _split_blocks(self, content: str) -> List[str]:
        blocks = re.split(r"\n{2,}", content.strip())
        return [b.strip() for b in blocks if b.strip()]

    def _parse_block(self, block: str) -> Optional[Dict]:
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if not lines:
            return None

        # Skip WEBVTT header / meta blocks
        if self._VTT_META_RE.match(lines[0]):
            return None

        # Find the timestamp line
        ts_match = None
        ts_line_idx = -1
        for i, line in enumerate(lines):
            m = self._TS_RE.search(line)
            if m:
                ts_match = m
                ts_line_idx = i
                break

        if ts_match is None:
            return None

        start = self._to_seconds(
            ts_match.group(1), ts_match.group(2),
            ts_match.group(3), ts_match.group(4)
        )
        end = self._to_seconds(
            ts_match.group(5), ts_match.group(6),
            ts_match.group(7), ts_match.group(8)
        )

        # Text lines follow the timestamp line
        text_lines = lines[ts_line_idx + 1:]
        # Strip VTT inline tags like <c>, <i>, <00:00:01.000>
        text_lines = [re.sub(r"<[^>]+>", "", l).strip() for l in text_lines if l.strip()]

        if not text_lines:
            return None

        raw_text = " ".join(text_lines)

        # Try to detect "Speaker: text" in the first line
        speaker = "Unknown"
        display_text = raw_text
        m_sp = self._SPEAKER_RE.match(text_lines[0])
        if m_sp:
            candidate = m_sp.group(1).strip()
            # Reject common false positives
            _NOT_SPEAKERS = {"the", "this", "that", "it", "he", "she", "they", "we", "i"}
            if candidate.lower().split()[0] not in _NOT_SPEAKERS and len(candidate.split()) <= 4:
                speaker = candidate
                rest = m_sp.group(2).strip()
                if len(text_lines) > 1:
                    rest += " " + " ".join(text_lines[1:])
                display_text = rest.strip()

        return {
            "id":      0,
            "start":   start,
            "end":     end,
            "text":    display_text,
            "speaker": speaker,
        }

    def _build_speaker_segments(self, segments: List[Dict]) -> List[Dict]:
        result: List[Dict] = []
        cur_speaker: Optional[str] = None
        cur_texts: List[str] = []
        cur_start = 0.0
        cur_end = 0.0

        for seg in segments:
            sp = seg.get("speaker", "Unknown")
            if sp != cur_speaker:
                if cur_texts:
                    result.append({
                        "speaker": cur_speaker,
                        "text":    " ".join(cur_texts),
                        "start":   cur_start,
                        "end":     cur_end,
                    })
                cur_speaker = sp
                cur_texts = [seg["text"]]
                cur_start = seg["start"]
                cur_end = seg["end"]
            else:
                cur_texts.append(seg["text"])
                cur_end = seg["end"]

        if cur_texts:
            result.append({
                "speaker": cur_speaker,
                "text":    " ".join(cur_texts),
                "start":   cur_start,
                "end":     cur_end,
            })
        return result

    def _build_speaker_stats(self, segments: List[Dict]) -> Dict:
        stats: Dict[str, Dict] = {}
        for seg in segments:
            sp = seg.get("speaker", "Unknown")
            if sp not in stats:
                stats[sp] = {"total_duration": 0.0, "segment_count": 0}
            stats[sp]["total_duration"] += seg["end"] - seg["start"]
            stats[sp]["segment_count"] += 1
        return stats

    @staticmethod
    def _to_seconds(h: str, m: str, s: str, ms: str) -> float:
        ms_val = int(ms.ljust(3, "0")[:3])
        return int(h) * 3600 + int(m) * 60 + int(s) + ms_val / 1000.0


# ── Convenience function ──────────────────────────────────────────────────────

def parse_srt(path: str) -> Dict:
    """
    Parse an SRT/VTT transcript file into Whisper-compatible format.

    Returns a dict with keys: text, language, segments, speaker_segments,
    speakers, total_speakers, source — same shape as AudioToTextConverter output.
    """
    return SRTParser().parse_to_transcript_dict(path)
