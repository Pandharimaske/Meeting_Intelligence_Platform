"""
RAG-based Minutes of Meeting Generator — v3.2

Changes in v3.2:
  - ROOT CAUSE FIX for duplicate responses: arcee-ai/trinity-large-preview:free (and
    other OpenRouter free models) return a FULL non-streaming response even when
    stream=True is sent. The OpenAI SDK wraps it as a single chunk, so the first
    token IS the full answer. We now detect this in _stream_openai_tokens and
    emit it as a FALLBACK sentinel immediately, preventing double-output.
  - Better action-item retrieval: explicit multi-query sweep across the full
    transcript, not just top-k RAG results.
  - _generate_section now uses top_k * 2 chunks for coverage-heavy sections
    (action_items, decisions, key_points, summary).
  - _CHAT_SYSTEM_PROMPT v2: stronger no-repeat / no-pad enforcement, cleaner
    action-item format guidance.
  - Clip scoring: boosted keyword weight, penalty for very short clips (<3s).
  - _format_context: now includes word count hint so LLM knows chunk density.
  - MoM section retrieval: 4 queries per section (was 2) for better recall.
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Generator, TYPE_CHECKING

if TYPE_CHECKING:
    from processing.vector.store import MeetingVectorStore


# ── System prompts ─────────────────────────────────────────────────────────────

_MOM_SYSTEM_PROMPT = """\
You are an expert meeting analyst and professional minute-taker.

CONTEXT
-------
You will receive excerpts from a real meeting transcript. Each excerpt is labelled
with a wall-clock timestamp range like [00:04:12 - 00:05:30] and, when available,
the speaker name(s) in parentheses.

YOUR JOB
--------
Extract structured, factual information from the excerpts and return it as valid JSON.

STRICT RULES
------------
1. Return ONLY the JSON object requested — no preamble, no explanation, no markdown fences.
2. NEVER invent, infer, or hallucinate facts not explicitly present in the excerpts.
3. When citing a moment, use the timestamp at the START of the excerpt where it appears.
4. Timestamps must be in HH:MM:SS format (e.g. "00:04:12", not "4:12").
5. Speaker names must be taken verbatim from the excerpt labels (e.g. "Speaker 0", "John").
   Use "Unknown" only if the speaker is genuinely unidentified.
6. Keep every field concise — no padding, no filler words.
7. If a section has no relevant content, return an empty array [].
"""

_CHAT_SYSTEM_PROMPT = """\
You are a sharp, precise AI assistant for meeting transcripts.

═══════════════════════════════════════════════════════
  ABSOLUTE RULES — VIOLATIONS ARE NEVER ACCEPTABLE
═══════════════════════════════════════════════════════
1. WRITE EACH IDEA EXACTLY ONCE. Never restate, rephrase, or paraphrase the
   same point. If you catch yourself repeating, delete the duplicate.
2. ANSWER FIRST. Put the direct answer in your first sentence. No preambles
   like "Based on the transcript..." or "According to the excerpts...".
3. HONEST ABOUT GAPS. If the information is not in the excerpts, say:
   "I couldn't find that in the transcript." — nothing more.
4. CONCISE. Under 180 words unless the user explicitly asked for a full summary.
5. NO PADDING. No filler phrases: "Certainly!", "Great question!", "It seems",
   "It appears that", "Based on the provided context".

═══════════════════════════════════════════════
  FORMATTING BY QUESTION TYPE
═══════════════════════════════════════════════
**Action items / tasks:**
  - List as bullets: "- **[Owner]**: task [HH:MM:SS]"
  - ONLY include tasks that were explicitly assigned to a named person.
  - Proposals, suggestions, and discussion points are NOT action items.
  - If genuinely none exist: "No explicit action items were assigned in this meeting."

**Decisions:**
  - List as bullets: "- Decision text [HH:MM:SS]"
  - Only include items explicitly agreed, approved, or committed to.
  - If none: "No formal decisions were made." (one sentence)

**Speakers / attendees:**
  - One bullet per speaker with their label and a 5-word role description.

**Summary** (only when user explicitly asked):
  ### Overview
  (2-3 sentences covering purpose, outcomes, next steps)
  ### Key Decisions
  ### Action Items

**All other questions:**
  - Prose answer with **bold** for key names/decisions.
  - Use [HH:MM:SS] inline when citing a moment.
  - Bullet list only if 3+ distinct items to enumerate.
"""

_CLIP_ANSWER_SYSTEM_PROMPT = """\
You are a meeting assistant. The user asked for a specific video clip.
Write ONE sentence (max 20 words) confirming what clip was found.
Format: "Here's [brief description] — [start_timestamp] to [end_timestamp]."
Do not add any other text. Be specific about what happens in the clip.
"""

_FOLLOWUPS_SYSTEM_PROMPT = """\
You generate short follow-up questions about a meeting. Return JSON only, no other text.
"""

_SPEAKER_NAMES_SYSTEM_PROMPT = """\
You extract real speaker names from meeting transcripts. Return JSON only, no other text.
"""


# ── Per-section prompts ────────────────────────────────────────────────────────

_SECTION_PROMPTS: Dict[str, str] = {

    "title": """\
Read the meeting excerpts below and write a SHORT, DESCRIPTIVE title (4–8 words).

EXCERPTS
--------
{context}

EXAMPLE OUTPUT: {{"title": "Q3 Product Roadmap Review and Prioritisation"}}
YOUR OUTPUT (JSON only):""",

    "agenda": """\
Identify the MAIN TOPICS discussed in the meeting excerpts below.
Ignore small talk, greetings, and off-topic tangents.

EXCERPTS
--------
{context}

EXAMPLE OUTPUT:
{{
  "agenda": [
    "Q3 revenue targets and budget allocation",
    "Mobile app launch timeline",
    "Hiring plan for engineering team"
  ]
}}

Return 3–7 noun-phrase topics. YOUR OUTPUT (JSON only):""",

    "key_points": """\
Extract the most IMPORTANT statements from the meeting excerpts below.
A key point = fact/figure, significant opinion, important update, or concern raised.
NOT a key point = small talk, logistics, or vague statements.

EXCERPTS
--------
{context}

EXAMPLE OUTPUT:
{{
  "key_points": [
    {{
      "timestamp": "00:03:45",
      "speaker": "Sarah",
      "point": "Monthly active users grew 34% in Q3, exceeding the 25% target"
    }}
  ]
}}

Extract up to 10 key points ordered by time. YOUR OUTPUT (JSON only):""",

    "decisions": """\
Extract every DECISION made in the meeting excerpts below.
A decision = explicit agreement, approval, or commitment to a course of action.
NOT a decision = ideas floated, hypotheticals, or questions asked.

EXCERPTS
--------
{context}

EXAMPLE OUTPUT:
{{
  "decisions": [
    {{"timestamp": "00:07:15", "decision": "Approved $50k budget increase for cloud infrastructure"}}
  ]
}}

If no decisions: {{"decisions": []}} YOUR OUTPUT (JSON only):""",

    "action_items": """\
Extract every ACTION ITEM or task that was explicitly assigned in the meeting excerpts below.
OWNER = the person the task was assigned to (use their name or speaker label).
TASK = specific action + deadline if mentioned.

IMPORTANT: Only extract EXPLICIT assignments — "I'll do X", "Can you do Y by Friday",
"[Name] will take care of Z". Do NOT include vague statements or proposals.

EXCERPTS
--------
{context}

EXAMPLE OUTPUT:
{{
  "action_items": [
    {{"timestamp": "00:15:30", "owner": "Marcus", "task": "Share updated project timeline with stakeholders by end of week"}},
    {{"timestamp": "00:22:10", "owner": "Sarah",  "task": "Draft the new onboarding checklist"}}
  ]
}}

If no explicit action items were assigned: {{"action_items": []}} YOUR OUTPUT (JSON only):""",

    "summary": """\
Write a concise EXECUTIVE SUMMARY of the meeting (3–5 sentences, third person past tense).
Cover: what the meeting was about, the most important outcome(s), and key next steps.
Do NOT start with "The meeting..." — vary your opening.

EXCERPTS
--------
{context}

EXAMPLE OUTPUT:
{{
  "summary": "Participants reviewed Q3 performance and approved a revised Q4 roadmap. Key decisions included prioritising the mobile checkout fix and delaying the analytics dashboard. Budget for additional infrastructure was approved pending finance sign-off."
}}

YOUR OUTPUT (JSON only):""",
}

# Four queries per section for better recall across the full transcript
_SECTION_QUERIES: Dict[str, List[str]] = {
    "title": [
        "purpose goal objective of this meeting",
        "meeting name topic overview agenda",
        "what is this meeting about",
        "meeting introduction opening remarks",
    ],
    "agenda": [
        "main topics subjects discussed covered in meeting",
        "what did they talk about meeting themes",
        "agenda items points covered today",
        "topics reviewed presented discussed",
    ],
    "key_points": [
        "important facts figures statistics updates shared",
        "significant statements announcements concerns raised",
        "key information data numbers results",
        "important findings insights observations",
    ],
    "decisions": [
        "decided agreed approved confirmed chosen selected committed",
        "we will go with let's do final decision consensus",
        "agreed to proceed with approved the plan",
        "outcome conclusion resolution agreed upon",
    ],
    "action_items": [
        "action items tasks assigned responsibilities owner deadline",
        "follow up next steps will do by needs to send prepare",
        "I will take care of can you please by Friday",
        "assigned to responsible for commit to deliver",
    ],
    "summary": [
        "overall summary what happened outcome result",
        "key takeaways main points conclusion",
        "meeting overview purpose what was discussed",
        "what was accomplished resolved decided in this meeting",
    ],
}

# Sections that benefit from wider chunk coverage (whole-meeting retrieval)
_WIDE_COVERAGE_SECTIONS = {"action_items", "decisions", "key_points", "summary"}


# ── Standalone: speaker name extraction ──────────────────────────────────────

def extract_speaker_names_from_segments(
    segments: List[Dict],
    backend: str,
    api_key: str,
    model: str,
    base_url: Optional[str] = None,
) -> Dict[str, str]:
    """
    Use LLM to extract real names from transcript segments.
    Looks for "I'm [Name]", "My name is [Name]", etc. patterns.

    Returns a mapping like: {"SPEAKER_00": "Laura", "SPEAKER_01": "David"}
    Only includes speakers where a name was confidently found.
    """
    if not segments or backend == "template":
        return {}

    lines = []
    for seg in segments[:40]:  # wider sample
        speaker = seg.get("speaker", "Unknown")
        text = seg.get("text", "").strip()[:120]
        if text:
            lines.append(f"[{speaker}]: {text}")

    context = "\n".join(lines)

    prompt = (
        "Find every place in this transcript where a speaker introduces themselves "
        "by name (e.g. 'I'm Laura', 'My name is David', 'Hi, I'm Andrew', "
        "'This is Marcus speaking').\n\n"
        f"TRANSCRIPT\n{'-'*20}\n{context}\n\n"
        "Return a JSON object mapping speaker labels to real first names.\n"
        "Use null for speakers whose name you cannot confidently determine.\n"
        'Example: {"SPEAKER_00": "Laura", "SPEAKER_01": "David", "SPEAKER_02": null}\n'
        "Return JSON only:"
    )

    try:
        if backend in ("openrouter", "openai"):
            from openai import OpenAI
            client = OpenAI(
                api_key=api_key,
                base_url=base_url or ("https://openrouter.ai/api/v1" if backend == "openrouter" else None),
            )
            resp = client.chat.completions.create(
                model=model,
                temperature=0.0,
                max_tokens=300,
                messages=[
                    {"role": "system", "content": _SPEAKER_NAMES_SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
            )
            raw = resp.choices[0].message.content.strip()
        elif backend == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            resp = client.messages.create(
                model=model,
                max_tokens=300,
                temperature=0.0,
                system=_SPEAKER_NAMES_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.content[0].text.strip()
        else:
            return {}

        cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
        start = cleaned.find("{")
        if start > 0:
            cleaned = cleaned[start:]
        mapping = json.loads(cleaned)
        return {k: v for k, v in mapping.items() if isinstance(v, str) and v.strip()}

    except Exception as e:
        print(f"  ⚠ Speaker name extraction failed: {e}")
        return {}


# ── RAGMoMGenerator ───────────────────────────────────────────────────────────

class RAGMoMGenerator:
    """
    Generates MoM and answers chat questions using per-section RAG + LLM.
    v3.2: root-cause fix for duplicate responses on non-streaming models.
    """

    def __init__(
        self,
        vector_store: "MeetingVectorStore",
        backend: str = "openrouter",
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        top_k: int = 6,
        score_threshold: float = 0.25,
        max_tokens: int = 2048,
        temperature: float = 0.1,
    ):
        self.store           = vector_store
        self.backend         = backend
        self.api_key         = api_key
        self.model           = model
        self.base_url        = base_url or "https://openrouter.ai/api/v1"
        self.top_k           = top_k
        self.score_threshold = score_threshold
        self.max_tokens      = max_tokens
        self.temperature     = temperature
        self._client         = None

    # ── Public API ────────────────────────────────────────────────────────

    def generate(self, output_path: Optional[str] = None) -> Dict:
        """Generate a full MoM by running RAG for each section."""
        print(f"  Generating MoM via RAG (backend='{self.backend}')...")
        mom: Dict = {}
        for section in ["title", "agenda", "key_points", "decisions", "action_items", "summary"]:
            print(f"    • {section}...")
            mom.update(self._generate_section(section))

        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(mom, f, indent=2)
            print(f"  ✓ MoM saved → '{output_path}'")

        return mom

    def answer_question(
        self,
        question: str,
        history: Optional[List[Dict]] = None,
    ) -> Tuple[str, bool]:
        """
        Non-streaming answer (backwards compatibility / template backend).
        Returns (answer_text, wants_clip).
        """
        q = question.strip()
        wants_clip = self._detect_clip_request(q)

        _GREETINGS = {"hi", "hii", "hello", "hey", "howdy", "greetings", "sup", "yo"}
        if q.lower().rstrip("!.,") in _GREETINGS:
            return (
                "Hello! I'm your meeting assistant. Try:\n"
                "- \"What was decided?\"\n"
                "- \"Summarise the meeting\"\n"
                "- \"Show me clip when [person/event]\"\n"
                "- \"What did [speaker] say about [topic]?\"",
                False,
            )

        if wants_clip:
            clips = self._find_clip_sources(q, top_n=3)
            answer = self._generate_clip_answer(q, clips)
            return (answer, True)

        context_chunks = self._get_chat_context(q, history or [])
        context = self._format_context(context_chunks[:14])
        meta = self._build_meeting_meta()
        history_block = self._build_history_block(history or [])

        prompt = (
            f"{meta}{history_block}"
            f"TRANSCRIPT EXCERPTS\n{'-'*20}\n{context}\n\n"
            f"QUESTION\n{'-'*20}\n{q}"
        )
        answer = self._call_llm_raw(prompt, system=_CHAT_SYSTEM_PROMPT)
        return (answer, False)

    def stream_events(
        self,
        question: str,
        history: Optional[List[Dict]] = None,
    ) -> Generator[Tuple[str, any], None, None]:
        """
        Synchronous generator for streaming chat responses.
        Yields (event_type, data) tuples:
          ("token",     str)           — text token from LLM
          ("sources",   List[Dict])    — relevant chunks (sent ONCE after streaming)
          ("clips",     List[Dict])    — clip chunks when wants_clip=True
          ("followups", List[str])     — follow-up question suggestions
          ("done",      None)          — stream complete
          ("error",     str)           — error message

        v3.2 DUPLICATE FIX:
        Some OpenRouter free models (e.g. arcee-ai/trinity-large-preview:free) do not
        truly stream — they return the full response as a single chunk even when
        stream=True is sent. The _stream_openai_tokens generator now detects this
        (first chunk contains the FULL answer) and emits a FALLBACK sentinel.
        stream_events() then emits the content exactly once regardless of whether it
        arrived via streaming or fallback path.
        """
        q = question.strip()

        # ── Greeting shortcut ──────────────────────────────────────────
        _GREETINGS = {"hi", "hii", "hello", "hey", "howdy", "greetings", "sup", "yo"}
        if q.lower().rstrip("!.,") in _GREETINGS:
            msg = (
                "Hello! I'm your meeting assistant. Try asking:\n"
                "- \"What was decided?\"\n"
                "- \"Summarise the meeting\"\n"
                "- \"Show me clip when [person/event]\"\n"
                "- \"What did [speaker] say about [topic]?\""
            )
            yield ("token", msg)
            yield ("done", None)
            return

        # ── Clip request ───────────────────────────────────────────────
        wants_clip = self._detect_clip_request(q)
        if wants_clip:
            try:
                clips = self._find_clip_sources(q, top_n=3)
                answer = self._generate_clip_answer(q, clips)
                yield ("token", answer)
                yield ("clips", clips)
                followups = self._generate_followups(q, answer)
                if followups:
                    yield ("followups", followups)
            except Exception as e:
                yield ("error", str(e))
            yield ("done", None)
            return

        # ── Normal chat: stream answer ─────────────────────────────────
        try:
            context_chunks = self._get_chat_context(q, history or [])
            context = self._format_context(context_chunks[:14])
            meta = self._build_meeting_meta()
            history_block = self._build_history_block(history or [])

            prompt = (
                f"{meta}{history_block}"
                f"TRANSCRIPT EXCERPTS\n{'-'*20}\n{context}\n\n"
                f"QUESTION\n{'-'*20}\n{q}"
            )

            full_answer = ""
            tokens_emitted = 0

            for token in self._stream_llm_tokens(prompt, system=_CHAT_SYSTEM_PROMPT):
                _SENTINEL = "\x00FALLBACK\x00"
                if token.startswith(_SENTINEL):
                    # Model returned full answer at once (non-streaming)
                    # Only emit if we haven't already sent tokens (avoids duplicates)
                    if tokens_emitted == 0:
                        fallback_text = token[len(_SENTINEL):]
                        full_answer = fallback_text
                        yield ("token", fallback_text)
                    # Either way, stop — don't emit again
                    break
                full_answer += token
                tokens_emitted += 1
                yield ("token", token)

            # Send sources exactly once, after streaming completes
            if context_chunks:
                # De-duplicate sources by chunk_id before sending
                seen_ids: set = set()
                unique_sources = []
                for c in context_chunks[:5]:
                    cid = c.get("chunk_id")
                    if cid not in seen_ids:
                        seen_ids.add(cid)
                        unique_sources.append(c)
                yield ("sources", unique_sources[:3])

            # Follow-up suggestions
            followups = self._generate_followups(q, full_answer[:400])
            if followups:
                yield ("followups", followups)

        except Exception as e:
            yield ("error", str(e))

        yield ("done", None)

    # ── Streaming LLM helpers ────────────────────────────────────────────

    def _stream_llm_tokens(
        self,
        prompt: str,
        system: str,
    ) -> Generator[str, None, None]:
        """
        Sync generator yielding text tokens from the LLM.

        v3.2 sentinel strategy:
        When a model returns the full response as a single chunk (non-streaming
        behaviour on a streaming endpoint), _stream_openai_tokens emits the
        sentinel prefix "\x00FALLBACK\x00<full_text>". The caller in stream_events
        handles this to emit content exactly once.
        """
        try:
            if self.backend == "openrouter":
                yield from self._stream_openai_tokens(
                    prompt, system, base_url=self.base_url,
                    extra_headers={
                        "HTTP-Referer": "https://github.com/meeting-intelligence-platform",
                        "X-Title": "Meeting Intelligence Platform",
                    }
                )
            elif self.backend == "openai":
                yield from self._stream_openai_tokens(prompt, system, base_url=None)
            elif self.backend == "anthropic":
                yield from self._stream_anthropic_tokens(prompt, system)
            else:
                result = self._call_llm_raw(prompt, system)
                yield f"\x00FALLBACK\x00{result}"
        except Exception as e:
            print(f"  ⚠ Streaming setup failed ({type(e).__name__}): {e} — using fallback")
            try:
                result = self._call_llm_raw(prompt, system)
                yield f"\x00FALLBACK\x00{result}"
            except Exception as e2:
                print(f"  ⚠ Fallback also failed: {e2}")
                yield "\x00FALLBACK\x00I encountered an error generating the response."

    def _stream_openai_tokens(
        self,
        prompt: str,
        system: str,
        base_url: Optional[str] = None,
        extra_headers: Optional[Dict] = None,
    ) -> Generator[str, None, None]:
        """
        v3.2: Detects pseudo-streaming (full response in first chunk) by checking
        if the very first token is suspiciously long (>80 chars). If so, the model
        isn't truly streaming — emit as FALLBACK sentinel so caller handles it once.
        """
        from openai import OpenAI
        client = OpenAI(api_key=self.api_key, base_url=base_url)
        model = self.model or (
            "arcee-ai/trinity-large-preview:free" if self.backend == "openrouter"
            else "gpt-3.5-turbo"
        )
        kwargs = dict(
            model=model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt},
            ],
            stream=True,
        )
        if extra_headers:
            kwargs["extra_headers"] = extra_headers

        stream = client.chat.completions.create(**kwargs)

        first_token_seen = False
        tokens_yielded = 0

        try:
            for chunk in stream:
                # Guard: some backends send usage/stats chunks with empty choices
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta is None:
                    continue
                token = delta.content
                if not token:
                    continue

                if not first_token_seen:
                    first_token_seen = True
                    # Heuristic: if the first "token" is very long, the model is
                    # returning the full answer at once (fake streaming).
                    # Threshold: 80 chars covers most real first tokens comfortably.
                    if len(token) > 80:
                        yield f"\x00FALLBACK\x00{token}"
                        # Drain remaining chunks silently (there may be empty deltas)
                        for _ in stream:
                            pass
                        return

                tokens_yielded += 1
                yield token

        except Exception as e:
            # Stream broke mid-way — log and stop cleanly
            print(f"  ⚠ Stream interrupted after {tokens_yielded} tokens: {e}")
            return

    def _stream_anthropic_tokens(
        self,
        prompt: str,
        system: str,
    ) -> Generator[str, None, None]:
        import anthropic
        client = anthropic.Anthropic(api_key=self.api_key)
        model = self.model or "claude-haiku-4-5-20251001"
        with client.messages.stream(
            model=model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                yield text

    # ── Context / history helpers ────────────────────────────────────────

    def _get_chat_context(
        self, question: str, history: List[Dict]
    ) -> List[Dict]:
        """
        Retrieve relevant chunks for a chat question.
        v3.2: wider retrieval for whole-meeting questions with evenly-spaced
        timeline coverage to prevent missing late-meeting action items/decisions.
        """
        q_lower = question.lower()

        is_whole_meeting = any(w in q_lower for w in {
            "summary", "summarise", "summarize", "overview", "recap",
            "brief", "tldr", "tl;dr", "what happened", "action item",
            "action items", "all action", "all tasks", "all decisions",
            "every decision", "who attended", "who were the speakers",
            "speakers", "all speakers", "list all", "list every",
        })

        queries = self._expand_chat_query(question)

        if is_whole_meeting:
            threshold = min(self.score_threshold, 0.08)
            top_k = min(self.top_k * 3, 20)
        else:
            threshold = min(self.score_threshold, 0.15)
            top_k = self.top_k

        chunks = self._retrieve_multi_with_threshold(
            queries, top_k=top_k, threshold=threshold,
        )

        # For whole-meeting questions: add evenly-spaced chunks for full coverage
        if is_whole_meeting:
            all_chunks = self.store._chunks
            n = min(12, len(all_chunks))
            if n > 0:
                step = max(1, len(all_chunks) // n)
                extra = [all_chunks[i] for i in range(0, len(all_chunks), step)][:n]
                seen = {c.get("chunk_id") for c in chunks}
                for c in extra:
                    if c.get("chunk_id") not in seen:
                        chunks.append(c)
                        seen.add(c.get("chunk_id"))

        return chunks

    def _build_history_block(self, history: List[Dict]) -> str:
        if not history:
            return ""
        turns = history[-6:]
        block = "CONVERSATION HISTORY\n" + "-" * 20 + "\n"
        for h in turns:
            role = "User" if h.get("role") == "user" else "Assistant"
            block += f"{role}: {h.get('content', '')}\n"
        return block + "\n"

    def _generate_followups(self, question: str, answer_snippet: str) -> List[str]:
        """
        Generate 2-3 concise follow-up questions using a quick LLM call.
        Returns empty list on failure or if backend is template.
        """
        if self.backend == "template":
            return []

        prompt = (
            f"Meeting Q&A:\nQ: {question}\nA: {answer_snippet[:250]}\n\n"
            "Suggest 2-3 short follow-up questions (under 8 words each) "
            "the user might want to ask next about this meeting.\n"
            "Focus on: decisions, action items, specific speakers, key moments.\n"
            'Return JSON only: {"followups": ["question 1", "question 2", "question 3"]}'
        )

        saved_max = self.max_tokens
        self.max_tokens = 200
        try:
            raw = self._call_llm_raw(prompt, system=_FOLLOWUPS_SYSTEM_PROMPT)
            result = self._parse_json(raw)
            followups = result.get("followups", [])
            return [str(f) for f in followups[:3] if isinstance(f, str) and len(f) > 3]
        except Exception:
            return []
        finally:
            self.max_tokens = saved_max

    # ── Smart clip search ────────────────────────────────────────────────

    def _find_clip_sources(self, question: str, top_n: int = 3) -> List[Dict]:
        entities = self._extract_entities(question)
        keywords = self._extract_keywords(question)
        queries  = self._expand_clip_query(question, entities)

        raw_results = []
        seen_ids: set = set()
        for q in queries:
            for chunk in self.store.search(q, top_k=min(20, len(self.store._chunks))):
                cid = chunk.get("chunk_id")
                if cid not in seen_ids:
                    seen_ids.add(cid)
                    raw_results.append(chunk)

        if not raw_results:
            return self.store._chunks[:min(2, len(self.store._chunks))]

        scored = [
            (self._combined_clip_score(c, entities, keywords), c)
            for c in raw_results
        ]
        scored = [(s, c) for s, c in scored if s > 0]
        scored.sort(key=lambda x: x[0], reverse=True)

        deduped = self._deduplicate_clips([c for _, c in scored])
        return deduped[:top_n]

    def _combined_clip_score(
        self, chunk: Dict, entities: List[str], keywords: List[str]
    ) -> float:
        text_lower   = chunk.get("raw_text", "").lower()
        vector_score = chunk.get("score", 0.0)

        entity_score = 0.0
        if entities:
            entity_score = sum(1 for e in entities if e.lower() in text_lower) / len(entities)

        keyword_score = 0.0
        if keywords:
            keyword_score = sum(1 for kw in keywords if kw.lower() in text_lower) / len(keywords)

        duration = chunk.get("duration", 10.0)
        # Stronger penalty for very short clips
        if duration < 3.0:
            length_penalty = 0.3
        elif duration < 5.0:
            length_penalty = 0.6
        else:
            length_penalty = 1.0

        return (
            0.40 * entity_score
            + 0.30 * vector_score
            + 0.30 * keyword_score
        ) * length_penalty

    def _deduplicate_clips(
        self, clips: List[Dict], overlap_threshold: float = 0.6
    ) -> List[Dict]:
        kept = []
        for clip in clips:
            overlaps = False
            for k in kept:
                inter = max(0.0, min(clip["end"], k["end"]) - max(clip["start"], k["start"]))
                min_dur = min(clip.get("duration", 1), k.get("duration", 1))
                if min_dur > 0 and inter / min_dur > overlap_threshold:
                    overlaps = True
                    break
            if not overlaps:
                kept.append(clip)
        return kept

    def _generate_clip_answer(self, question: str, clips: List[Dict]) -> str:
        if not clips:
            return "I couldn't find a relevant clip for that in the transcript."

        best = clips[0]
        ts_range = f"{best['start_timestamp']} – {best['end_timestamp']}"
        snippet  = best.get("raw_text", "")[:200].replace("\n", " ")
        prompt   = (
            f'User asked: "{question}"\n'
            f'Best clip: [{ts_range}] — "{snippet}"\n'
            "Write ONE confirmation sentence (max 20 words)."
        )
        try:
            answer = self._call_llm_raw(prompt, system=_CLIP_ANSWER_SYSTEM_PROMPT)
            answer = answer.split("\n")[0].strip()
            return answer if len(answer) >= 5 else f"Here's the matching clip — {ts_range}."
        except Exception:
            return f"Here's the matching clip — {ts_range}."

    # ── Entity / keyword extraction ──────────────────────────────────────

    def _extract_entities(self, question: str) -> List[str]:
        _STOP = {
            "Show", "Me", "Clip", "When", "Where", "What", "Who", "How",
            "The", "A", "An", "In", "At", "By", "Of", "For", "To", "And",
            "Is", "Are", "Was", "Were", "Did", "Does", "Do", "Please",
            "Find", "Get", "Play", "Give", "Tell", "Can", "Could",
        }
        words = re.findall(r"\b[A-Z][a-zA-Z]{1,20}\b", question)
        return [w for w in words if w not in _STOP]

    def _extract_keywords(self, question: str) -> List[str]:
        _STRIP = re.compile(
            r"\b(show|me|clip|when|where|what|who|how|did|was|were|is|are|can|could|"
            r"please|find|get|play|give|tell|the|a|an|in|at|by|of|for|to|and|or|"
            r"this|that|his|her|their|its|himself|herself|themselves|"
            r"introduced|introducing|introduction|said|says|talked|mentioned|"
            r"moment|segment|part|section|time|point)\b",
            re.IGNORECASE,
        )
        cleaned = _STRIP.sub(" ", question)
        words = re.findall(r"\b[a-zA-Z]{3,}\b", cleaned)
        return [w.lower() for w in words if len(w) > 2]

    def _expand_clip_query(self, question: str, entities: List[str]) -> List[str]:
        queries = [question]
        if entities:
            queries.append(" ".join(entities) + " introduced themselves spoke said")
        keyword_q = re.sub(
            r"^(show me|play|find|get|clip of|clip when|clip where|show clip|give me clip)\s+",
            "", question, flags=re.IGNORECASE
        ).strip("?. ")
        if keyword_q and keyword_q.lower() != question.lower():
            queries.append(keyword_q)
        return queries[:3]

    # ── General chat helpers ─────────────────────────────────────────────

    def _detect_clip_request(self, question: str) -> bool:
        q = question.lower().strip()
        clip_patterns = [
            r"\bshow\b.*\bclip\b",
            r"\bplay\b.*\bclip\b",
            r"\bclip\b.*\bwhen\b",
            r"\bclip\b.*\bwhere\b",
            r"\bgive me.*clip\b",
            r"\bshow me\b.*\bwhen\b",
            r"\bshow me\b.*\bwhere\b",
            r"\bshow me\b.*\bsegment\b",
            r"\bshow me\b.*\bpart\b",
            r"\bplay.*when\b",
            r"\bwatch\b.*\bwhen\b",
            r"\bjump to\b",
            r"\bskip to\b",
            r"\bgo to.*where\b",
        ]
        return any(re.search(p, q) for p in clip_patterns)

    def _expand_chat_query(self, question: str) -> List[str]:
        """Richer query expansion covering major question types."""
        q = question.strip()
        q_lower = q.lower()
        variants = [q]

        keyword_q = re.sub(
            r"^(what|who|when|where|how|did|was|were|is|are|can|could|tell me about|"
            r"summarize|summarise|explain|describe|list|give me|show me)\s+",
            "", q, flags=re.IGNORECASE
        ).strip("?. ")
        if keyword_q and keyword_q.lower() != q_lower:
            variants.append(keyword_q)

        if any(w in q_lower for w in ["action", "task", "todo", "to-do", "assigned", "owner", "responsible"]):
            variants.append("action items tasks assigned owner responsible follow up")

        if any(w in q_lower for w in ["decision", "decided", "agreed", "approved", "final", "conclusion"]):
            variants.append("decided agreed approved committed final decision outcome")

        if any(w in q_lower for w in ["speaker", "who", "attendee", "participant", "present", "attended"]):
            variants.append("speaker participant attendee introduced hello name")

        if any(w in q_lower for w in ["summary", "summarise", "summarize", "overview", "recap", "happened"]):
            variants.append("meeting overview main topics discussed key points outcomes")

        return variants[:4]

    def _build_meeting_meta(self) -> str:
        all_chunks = self.store._chunks
        if not all_chunks:
            return ""
        first = min(all_chunks, key=lambda c: c["start"])
        last  = max(all_chunks, key=lambda c: c["end"])
        total = last["end"] - first["start"]
        h, m, s = int(total // 3600), int((total % 3600) // 60), int(total % 60)
        duration_str = f"{h}h {m}m {s}s" if h > 0 else f"{m}m {s}s"
        speakers = sorted({
            sp for c in all_chunks for sp in c.get("speakers", []) if sp and sp != "Unknown"
        })
        speaker_line = f"Speakers: {', '.join(speakers)}\n" if speakers else ""
        return (
            f"MEETING METADATA\n{'-'*16}\n"
            f"Start   : {first['start_timestamp']}\n"
            f"End     : {last['end_timestamp']}\n"
            f"Length  : {duration_str}\n"
            f"Chunks  : {len(all_chunks)}\n"
            f"{speaker_line}\n"
        )

    # ── Retrieval ────────────────────────────────────────────────────────

    def _retrieve_multi(self, queries: List[str], top_k: int) -> List[Dict]:
        seen: set = set()
        merged: List[Dict] = []
        for q in queries:
            for chunk in self.store.search(q, top_k=top_k):
                if chunk.get("score", 0) < self.score_threshold:
                    continue
                cid = chunk.get("chunk_id")
                if cid not in seen:
                    seen.add(cid)
                    merged.append(chunk)
        return merged

    def _retrieve_multi_with_threshold(
        self, queries: List[str], top_k: int, threshold: float
    ) -> List[Dict]:
        seen: set = set()
        merged: List[Dict] = []
        for q in queries:
            for chunk in self.store.search(q, top_k=top_k):
                if chunk.get("score", 0) < threshold:
                    continue
                cid = chunk.get("chunk_id")
                if cid not in seen:
                    seen.add(cid)
                    merged.append(chunk)
        return merged

    def _format_context(self, chunks: List[Dict]) -> str:
        lines = []
        for i, chunk in enumerate(sorted(chunks, key=lambda c: c["start"]), 1):
            ts       = f"[{chunk['start_timestamp']} - {chunk['end_timestamp']}]"
            speakers = chunk.get("speakers", [])
            sp       = f" ({', '.join(speakers)})" if speakers else ""
            wc       = chunk.get("word_count", 0)
            wc_hint  = f" ~{wc}w" if wc else ""
            lines.append(f"Excerpt {i} {ts}{sp}{wc_hint}:\n{chunk['raw_text'].strip()}\n")
        return "\n".join(lines)

    # ── Section generation (MoM) ─────────────────────────────────────────

    def _generate_section(self, section: str) -> Dict:
        queries = _SECTION_QUERIES[section]

        # Wide coverage sections get more chunks
        if section in _WIDE_COVERAGE_SECTIONS:
            fetch_k = min(self.top_k * 2, 14)
        else:
            fetch_k = self.top_k

        chunks = self._retrieve_multi(queries, top_k=fetch_k)

        # Always have at least some context
        if not chunks:
            chunks = self.store._chunks[:6]

        # For coverage-heavy sections, supplement with evenly-spaced chunks
        if section in _WIDE_COVERAGE_SECTIONS:
            all_chunks = self.store._chunks
            n = min(8, len(all_chunks))
            if n > 0:
                step = max(1, len(all_chunks) // n)
                extra = [all_chunks[i] for i in range(0, len(all_chunks), step)]
                seen = {c.get("chunk_id") for c in chunks}
                for c in extra:
                    if c.get("chunk_id") not in seen:
                        chunks.append(c)
                        seen.add(c.get("chunk_id"))

        context = self._format_context(chunks)
        prompt  = _SECTION_PROMPTS[section].format(context=context)
        raw     = self._call_llm_raw(prompt, system=_MOM_SYSTEM_PROMPT)
        return self._parse_json(raw)

    # ── LLM calls (non-streaming) ────────────────────────────────────────

    def _call_llm_raw(self, prompt: str, system: Optional[str] = None) -> str:
        sys_prompt = system or _MOM_SYSTEM_PROMPT
        try:
            if self.backend == "openrouter":
                return self._call_openrouter(prompt, sys_prompt)
            elif self.backend == "anthropic":
                return self._call_anthropic(prompt, sys_prompt)
            elif self.backend == "openai":
                return self._call_openai(prompt, sys_prompt)
            else:
                raise ValueError(f"Unknown backend '{self.backend}'.")
        except Exception as e:
            print(f"  ⚠️  LLM call failed ({type(e).__name__}): {str(e)[:120]}")
            return self._template_fallback(prompt)

    def _call_openrouter(self, prompt: str, system: str) -> str:
        from openai import OpenAI
        if self._client is None:
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        model = self.model or "arcee-ai/trinity-large-preview:free"
        response = self._client.chat.completions.create(
            model=model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            extra_headers={
                "HTTP-Referer": "https://github.com/meeting-intelligence-platform",
                "X-Title": "Meeting Intelligence Platform",
            },
        )
        return response.choices[0].message.content.strip()

    def _call_anthropic(self, prompt: str, system: str) -> str:
        import anthropic
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self.api_key)
        model = self.model or "claude-haiku-4-5-20251001"
        response = self._client.messages.create(
            model=model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()

    def _call_openai(self, prompt: str, system: str) -> str:
        from openai import OpenAI
        if self._client is None:
            self._client = OpenAI(api_key=self.api_key)
        model = self.model or "gpt-3.5-turbo"
        response = self._client.chat.completions.create(
            model=model,
            temperature=self.temperature,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()

    # ── JSON parsing ──────────────────────────────────────────────────────

    def _parse_json(self, raw: str) -> Dict:
        cleaned = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
        cleaned = cleaned.lstrip("\ufeff\u200b")
        brace = cleaned.find("{")
        bracket = cleaned.find("[")
        start = -1
        if brace != -1 and (bracket == -1 or brace < bracket):
            start = brace
        elif bracket != -1:
            start = bracket
        if start > 0:
            cleaned = cleaned[start:]
        cleaned = re.sub(r",\s*([\]\}])", r"\1", cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            print(f"    ⚠ JSON parse failed: {e} — snippet: {cleaned[:120]!r}")
            return {}

    def _template_fallback(self, prompt: str) -> str:
        p = prompt.lower()
        if '"agenda"' in p or "main topics" in p:
            return json.dumps({"agenda": ["General discussion", "Planning", "Next steps"]})
        if "key_points" in p:
            return json.dumps({"key_points": []})
        if '"decisions"' in p:
            return json.dumps({"decisions": []})
        if "action_items" in p:
            return json.dumps({"action_items": []})
        if '"title"' in p:
            return json.dumps({"title": "Meeting Minutes"})
        return json.dumps({"summary": "Meeting summary not available — LLM backend unreachable."})
