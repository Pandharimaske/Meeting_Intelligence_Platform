import json
from pathlib import Path
from typing import List, Dict, Optional


# ------------------------------------------------------------------
# Prompt templates
# ------------------------------------------------------------------

_MOM_SYSTEM_PROMPT = """You are a professional meeting secretary.
Your job is to read a meeting transcript and produce a structured Minutes of Meeting (MoM).
Every line of the transcript begins with a timestamp like [00:01:23 - 00:02:45].
You MUST cite the timestamp when referencing a decision or action item.
Be concise and factual. Do not invent information not present in the transcript."""


_MOM_USER_PROMPT = """Below is the full transcript of a meeting, split into time-stamped sections.

{transcript}

---

Please produce a Minutes of Meeting in the following exact JSON format:

{{
  "title": "Brief descriptive title of the meeting",
  "agenda": ["topic 1", "topic 2", ...],
  "key_points": [
    {{"timestamp": "HH:MM:SS", "speaker": "Speaker name or Unknown", "point": "what was said"}}
  ],
  "decisions": [
    {{"timestamp": "HH:MM:SS", "decision": "what was decided"}}
  ],
  "action_items": [
    {{"timestamp": "HH:MM:SS", "owner": "SPEAKER_ID or Unknown", "task": "what they must do"}}
  ],
  "summary": "2-3 sentence overall summary of the meeting"
}}

Return ONLY valid JSON. No explanation, no markdown fences."""


# ------------------------------------------------------------------
# MoMGenerator class
# ------------------------------------------------------------------

class MoMGenerator:
    """
    Generates structured Minutes of Meeting from transcript chunks.

    Supports two backends:
      - "anthropic" : Claude via the anthropic SDK  (best quality)
      - "openai"    : OpenAI ChatGPT via openai SDK
      - "template"  : No LLM — rule-based extraction  (fallback, no API key needed)
    """

    def __init__(self, backend: str = "template", api_key: Optional[str] = None, model: Optional[str] = None):
        """
        Args:
            backend:  "anthropic" | "openai" | "template"
            api_key:  API key for the chosen backend (not needed for template).
            model:    Model name override. Defaults to claude-3-haiku / gpt-3.5-turbo.
        """
        self.backend = backend
        self.api_key = api_key
        self.model = model
        self._client = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, chunks: List[Dict], output_path: Optional[str] = None) -> Dict:
        """
        Generate MoM from a list of transcript chunks.

        Args:
            chunks:      Output of TranscriptChunker.chunk_transcript().
            output_path: If provided, save the MoM JSON to this file path.

        Returns:
            MoM as a Python dict.
        """
        if not chunks:
            raise ValueError("No chunks provided.")

        transcript_text = self._chunks_to_transcript(chunks)

        print(f"  Generating MoM using backend='{self.backend}'...")

        if self.backend == "anthropic":
            mom = self._generate_anthropic(transcript_text)
        elif self.backend == "openai":
            mom = self._generate_openai(transcript_text)
        else:
            mom = self._generate_template(chunks)

        # Always add timestamp citations to action items if missing
        mom = self._ensure_citations(mom, chunks)

        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(mom, f, indent=2)
            print(f"  ✓ MoM saved to '{output_path}'")

        return mom

    def pretty_print(self, mom: Dict) -> str:
        """Return a human-readable string version of the MoM."""
        lines = []
        lines.append("=" * 60)
        lines.append(f"  MINUTES OF MEETING: {mom.get('title', 'Untitled')}")
        lines.append("=" * 60)

        lines.append("\n📋 AGENDA")
        for item in mom.get("agenda", []):
            lines.append(f"   • {item}")

        lines.append("\n🗝  KEY POINTS")
        for kp in mom.get("key_points", []):
            ts = kp.get("timestamp", "")
            sp = kp.get("speaker", "")
            pt = kp.get("point", "")
            lines.append(f"   [{ts}] {sp}: {pt}")

        lines.append("\n✅ DECISIONS")
        for d in mom.get("decisions", []):
            lines.append(f"   [{d.get('timestamp', '')}] {d.get('decision', '')}")

        lines.append("\n📌 ACTION ITEMS")
        for a in mom.get("action_items", []):
            lines.append(f"   [{a.get('timestamp', '')}] {a.get('owner', 'Unknown')} → {a.get('task', '')}")

        lines.append("\n📝 SUMMARY")
        lines.append(f"   {mom.get('summary', '')}")
        lines.append("=" * 60)

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Backends
    # ------------------------------------------------------------------

    def _generate_anthropic(self, transcript_text: str) -> Dict:
        try:
            import anthropic
        except ImportError:
            raise ImportError("Run: pip install anthropic")

        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self.api_key)

        model = self.model or "claude-haiku-4-5-20251001"
        response = self._client.messages.create(
            model=model,
            max_tokens=2048,
            system=_MOM_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _MOM_USER_PROMPT.format(transcript=transcript_text)}]
        )
        raw = response.content[0].text.strip()
        return self._parse_json(raw)

    def _generate_openai(self, transcript_text: str) -> Dict:
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("Run: pip install openai")

        if self._client is None:
            self._client = OpenAI(api_key=self.api_key)

        model = self.model or "gpt-3.5-turbo"
        response = self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _MOM_SYSTEM_PROMPT},
                {"role": "user", "content": _MOM_USER_PROMPT.format(transcript=transcript_text)}
            ],
            temperature=0.2
        )
        raw = response.choices[0].message.content.strip()
        return self._parse_json(raw)

    def _generate_template(self, chunks: List[Dict]) -> Dict:
        """
        Rule-based MoM extraction — no LLM required.
        Simple heuristics: keyword spotting for decisions and action items.
        Good enough for testing; replace with an LLM backend for production.
        """
        decision_keywords = [
            "decided", "decision", "agreed", "going with", "confirmed",
            "let's go with", "settle on", "chosen", "picked", "selected",
            "stick with", "makes sense", "good idea", "let's do",
            "we've agreed", "consensus", "that's decided", "final decision",
            "we'll go", "that'll be", "committed to"
        ]
        action_keywords = [
            "you're going to", "you will", "needs to", "action", "follow up",
            "take care", "responsible", "i'll", "he'll", "she'll", "they'll",
            "next meeting", "by next", "send", "prepare", "work on",
            "look into", "check", "find out", "come up with", "report back"
        ]

        key_points = []
        decisions = []
        action_items = []

        for chunk in chunks:
            text = chunk["raw_text"].lower()
            ts = chunk["start_timestamp"]
            speakers = chunk.get("speakers", ["Unknown"])
            speaker = speakers[0] if speakers else "Unknown"

            # Key point: every chunk contributes a summary point
            first_sentence = chunk["raw_text"].split(".")[0].strip()
            if len(first_sentence) > 20:
                key_points.append({"timestamp": ts, "speaker": speaker, "point": first_sentence})

            # Decision detection
            if any(kw in text for kw in decision_keywords):
                decisions.append({"timestamp": ts, "decision": chunk["raw_text"][:200]})

            # Action item detection
            if any(kw in text for kw in action_keywords):
                action_items.append({"timestamp": ts, "owner": speaker, "task": chunk["raw_text"][:200]})

        # Build a simple summary from first and last chunks
        all_text = " ".join(c["raw_text"] for c in chunks)
        word_count = len(all_text.split())
        summary = (
            f"Meeting transcript contains {len(chunks)} segments covering approximately "
            f"{word_count} words. "
            f"Started at {chunks[0]['start_timestamp']} and ended at {chunks[-1]['end_timestamp']}. "
            f"Topics included: {', '.join(self._extract_topics(chunks))}."
        )

        return {
            "title": "Meeting Minutes",
            "agenda": self._extract_topics(chunks),
            "key_points": key_points[:10],
            "decisions": decisions[:10],
            "action_items": action_items[:10],
            "summary": summary
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _chunks_to_transcript(self, chunks: List[Dict]) -> str:
        """Format chunks as a readable transcript string for the LLM prompt."""
        lines = []
        for chunk in chunks:
            ts = f"[{chunk['start_timestamp']} - {chunk['end_timestamp']}]"
            speakers = chunk.get("speakers", [])
            sp_label = f" ({', '.join(speakers)})" if speakers else ""
            lines.append(f"{ts}{sp_label}\n{chunk['raw_text']}\n")
        return "\n".join(lines)

    def _parse_json(self, raw: str) -> Dict:
        """Strip markdown fences and parse JSON from LLM response."""
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            print(f"  Warning: Could not parse LLM response as JSON: {e}")
            return {
                "title": "Meeting Minutes",
                "agenda": [],
                "key_points": [],
                "decisions": [],
                "action_items": [],
                "summary": raw[:500]
            }

    def _ensure_citations(self, mom: Dict, chunks: List[Dict]) -> Dict:
        """Add timestamp to any action item or decision missing one."""
        for item in mom.get("action_items", []) + mom.get("decisions", []):
            if not item.get("timestamp") and chunks:
                item["timestamp"] = chunks[0]["start_timestamp"]
        return mom

    def _extract_topics(self, chunks: List[Dict]) -> List[str]:
        """Naive topic extraction: find most frequent non-stopword nouns."""
        stopwords = {
            "the", "a", "an", "is", "it", "in", "on", "at", "to", "of", "for",
            "and", "or", "we", "i", "you", "that", "this", "um", "uh", "be",
            "so", "just", "like", "yeah", "okay", "right", "well", "know",
            "think", "what", "have", "with", "they", "from", "but", "not",
            "are", "was", "were", "been", "has", "had", "will", "would",
            "could", "should", "may", "might", "can", "do", "did", "does",
            "if", "as", "by", "about", "there", "their", "then", "than",
            "when", "which", "who", "how", "some", "more", "want", "going",
            "get", "got", "its", "our", "your", "mean", "that's", "it's",
            "don't", "i'm", "we're", "i've", "it'll", "he's", "she's",
            "actually", "really", "very", "kind", "thing", "something",
            "anything", "because", "maybe", "even", "also", "one",
            "good", "other", "animal", "animals", "people", "here",
            "well", "now", "them", "these", "those", "make", "made",
            "take", "come", "back", "much", "many", "time", "way",
            "okay", "uh", "just", "yeah", "right", "think", "know"
        }
        word_freq: Dict[str, int] = {}
        for chunk in chunks:
            for word in chunk["raw_text"].lower().split():
                word = word.strip(".,?!'\"")
                if word and word not in stopwords and len(word) > 3:
                    word_freq[word] = word_freq.get(word, 0) + 1

        top = sorted(word_freq, key=lambda w: word_freq[w], reverse=True)[:5]
        return top


# ------------------------------------------------------------------
# Convenience function
# ------------------------------------------------------------------

def generate_mom(
    chunks: List[Dict],
    backend: str = "template",
    api_key: Optional[str] = None,
    output_path: Optional[str] = None
) -> Dict:
    """
    Generate Minutes of Meeting from transcript chunks.

    Args:
        chunks:      Output of TranscriptChunker.chunk_transcript().
        backend:     "template" | "anthropic" | "openai"
        api_key:     API key for LLM backend (not needed for template).
        output_path: Optional path to save the MoM JSON.

    Returns:
        MoM as a Python dict.
    """
    generator = MoMGenerator(backend=backend, api_key=api_key)
    return generator.generate(chunks, output_path=output_path)
