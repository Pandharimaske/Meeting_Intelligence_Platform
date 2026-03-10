"""
RAG-based Minutes of Meeting Generator — improved prompts.

Architecture:
  For each MoM section (title, agenda, key_points, decisions, action_items, summary),
  we run a targeted semantic search against the FAISS vector store to retrieve
  only the most relevant chunks, then send those chunks + a focused prompt to the LLM.

  Improvements over v1:
  - Richer system prompt with explicit output contract and anti-hallucination rules
  - Few-shot examples in every section prompt → consistent JSON shapes
  - Key-points prompt distinguishes signal from filler
  - Action-items prompt enforces owner extraction from speaker context
  - Query expansion for retrieval: each section uses 2 complementary queries
  - Chat uses a dedicated system prompt that frames the assistant as a meeting expert
  - Robust JSON repair: handles partial markdown fences, trailing commas, etc.
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from src.vector_store.store import MeetingVectorStore


# ── System prompt ─────────────────────────────────────────────────────────────

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
7. If a section has no relevant content (e.g. no decisions were made), return an empty array [].
"""


_CHAT_SYSTEM_PROMPT = """\
You are a knowledgeable meeting assistant with access to the transcript of a specific meeting.

YOUR JOB
--------
Answer the user's question accurately using ONLY the transcript excerpts provided.
Cite timestamps in [HH:MM:SS] format whenever you reference a specific moment.

RULES
-----
1. Base every claim on the excerpts — never invent or extrapolate.
2. If the answer is not in the excerpts, say clearly: "The transcript doesn't cover that."
3. If the question is ambiguous, answer the most likely intent and note the ambiguity.
4. Be concise and direct. Avoid padding.
5. Format your answer in plain text — no markdown, no bullet points unless the question asks for a list.
"""


# ── Per-section prompts with few-shot examples ────────────────────────────────

_SECTION_PROMPTS: Dict[str, str] = {

    # ── title ─────────────────────────────────────────────────────────────────
    "title": """\
Read the meeting excerpts below and write a SHORT, DESCRIPTIVE title (4–8 words).
The title should convey the meeting's primary purpose or outcome.

EXCERPTS
--------
{context}

EXAMPLE OUTPUT
--------------
{{"title": "Q3 Product Roadmap Review and Prioritisation"}}

YOUR OUTPUT (JSON only):""",

    # ── agenda ────────────────────────────────────────────────────────────────
    "agenda": """\
Identify the MAIN TOPICS that were discussed in the meeting excerpts below.
List only genuine discussion topics — ignore small talk, greetings, and off-topic tangents.

EXCERPTS
--------
{context}

EXAMPLE OUTPUT
--------------
{{
  "agenda": [
    "Q3 revenue targets and budget allocation",
    "Mobile app launch timeline",
    "Hiring plan for engineering team",
    "Customer feedback on v2.0 release"
  ]
}}

Return 3–7 topics. Each topic should be a noun phrase, not a full sentence.

YOUR OUTPUT (JSON only):""",

    # ── key_points ────────────────────────────────────────────────────────────
    "key_points": """\
Extract the most IMPORTANT and SUBSTANTIVE statements from the meeting excerpts below.

A key point is:
  ✓ A fact, figure, or statistic that was shared
  ✓ A significant opinion or position that shaped the discussion
  ✓ An important update or piece of news
  ✓ A concern or risk that was raised

A key point is NOT:
  ✗ Small talk or pleasantries ("Good morning everyone")
  ✗ Meeting logistics ("Let's move to the next item")
  ✗ Vague statements with no substance ("Things are going well")
  ✗ Repetitions of something already captured

EXCERPTS
--------
{context}

EXAMPLE OUTPUT
--------------
{{
  "key_points": [
    {{
      "timestamp": "00:03:45",
      "speaker": "Sarah",
      "point": "Monthly active users grew 34% in Q3, exceeding the 25% target"
    }},
    {{
      "timestamp": "00:11:20",
      "speaker": "Unknown",
      "point": "Backend latency is causing checkout failures on mobile — affects roughly 8% of sessions"
    }}
  ]
}}

Extract up to 8 key points, ordered by the time they appear.

YOUR OUTPUT (JSON only):""",

    # ── decisions ─────────────────────────────────────────────────────────────
    "decisions": """\
Extract every DECISION that was made or agreed upon in the meeting excerpts below.

A decision is a moment where the group:
  ✓ Explicitly agreed on a course of action ("We'll go with option B")
  ✓ Confirmed or approved something ("Budget approved", "Design signed off")
  ✓ Chose between alternatives ("We're selecting vendor X")
  ✓ Committed to a direction ("We're targeting a Q4 launch")

Do NOT include:
  ✗ Ideas that were merely discussed but not decided
  ✗ Suggestions or proposals without clear agreement
  ✗ Questions that were raised but not answered

EXCERPTS
--------
{context}

EXAMPLE OUTPUT
--------------
{{
  "decisions": [
    {{
      "timestamp": "00:07:15",
      "decision": "Approved $50k budget increase for cloud infrastructure"
    }},
    {{
      "timestamp": "00:22:40",
      "decision": "Selected React Native over Flutter for the mobile rewrite"
    }}
  ]
}}

If there are no clear decisions, return: {{"decisions": []}}

YOUR OUTPUT (JSON only):""",

    # ── action_items ──────────────────────────────────────────────────────────
    "action_items": """\
Extract every ACTION ITEM, task, or responsibility that was assigned in the meeting excerpts below.

An action item is:
  ✓ A specific task someone was asked or committed to do
  ✓ A follow-up with a clear next step
  ✓ Something with an implicit or explicit deadline

For the OWNER field:
  • Use the speaker's name exactly as it appears in the excerpt labels
  • If a task was assigned TO someone (e.g. "John, can you..."), use that person's name
  • If ownership is genuinely unclear, use "Unknown"

For the TASK field:
  • Be specific about WHAT needs to be done
  • Include deadline or target date if mentioned (e.g. "by Friday", "before next meeting")

EXCERPTS
--------
{context}

EXAMPLE OUTPUT
--------------
{{
  "action_items": [
    {{
      "timestamp": "00:15:30",
      "owner": "Marcus",
      "task": "Share updated project timeline with all stakeholders by end of week"
    }},
    {{
      "timestamp": "00:28:10",
      "owner": "Engineering Team",
      "task": "Investigate checkout failure root cause and report findings at next standup"
    }}
  ]
}}

If there are no action items, return: {{"action_items": []}}

YOUR OUTPUT (JSON only):""",

    # ── summary ───────────────────────────────────────────────────────────────
    "summary": """\
Write a concise EXECUTIVE SUMMARY of the meeting based on the excerpts below.

Requirements:
  • 3–4 sentences maximum
  • Cover: what the meeting was about, the most important outcome or decision, and key next steps
  • Write in third person, past tense ("The team discussed...", "It was decided...")
  • Do NOT list every detail — focus on the headline story
  • Do NOT start with "The meeting..." — vary the opening

EXCERPTS
--------
{context}

EXAMPLE OUTPUT
--------------
{{
  "summary": "The product team reviewed Q3 performance and approved a revised roadmap for Q4. Key decisions included prioritising the mobile checkout fix and delaying the analytics dashboard by two sprints. Budget for additional infrastructure was approved, and several action items were assigned to address the backlog of customer-reported issues."
}}

YOUR OUTPUT (JSON only):""",
}


# ── RAG queries per section (dual-query expansion) ────────────────────────────
# Two complementary queries per section — results are merged and deduplicated.
# This catches relevant chunks that a single query might miss.

_SECTION_QUERIES: Dict[str, Tuple[str, str]] = {
    "title":        ("purpose goal objective of this meeting",
                     "meeting name topic overview agenda"),
    "agenda":       ("main topics subjects discussed covered in meeting",
                     "what did they talk about meeting themes"),
    "key_points":   ("important facts figures statistics updates shared",
                     "significant statements announcements concerns raised"),
    "decisions":    ("decided agreed approved confirmed chosen selected committed",
                     "we will go with let's do final decision consensus"),
    "action_items": ("action items tasks assigned responsibilities owner deadline",
                     "follow up next steps will do by needs to send prepare"),
    "summary":      ("overall summary what happened outcome result",
                     "key takeaways main points conclusion"),
}


# ── RAGMoMGenerator ───────────────────────────────────────────────────────────

class RAGMoMGenerator:
    """
    Generates structured Minutes of Meeting using per-section RAG + LLM calls.
    Supports backends: openrouter | anthropic | openai
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

    # ── Public API ────────────────────────────────────────────────

    def generate(self, output_path: Optional[str] = None) -> Dict:
        """Generate a full MoM by running RAG for each section."""
        print(f"  Generating MoM via RAG (backend='{self.backend}')...")

        mom: Dict = {}
        for section in ["title", "agenda", "key_points", "decisions", "action_items", "summary"]:
            print(f"    • {section}...")
            result = self._generate_section(section)
            mom.update(result)

        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(mom, f, indent=2)
            print(f"  ✓ MoM saved → '{output_path}'")

        return mom

    def answer_question(self, question: str, history: Optional[List[Dict]] = None) -> str:
        """
        Answer a free-form question about the meeting using RAG.

        Args:
            question: Natural language question.
            history:  Optional list of {role, content} dicts for multi-turn context.

        Returns:
            Plain-text answer with timestamp citations.
        """
        # Expand query with rephrasing for better retrieval coverage
        queries = self._expand_chat_query(question)
        chunks  = self._retrieve_multi(queries, top_k=self.top_k)

        if not chunks:
            return "The transcript doesn't contain information relevant to that question."

        context = self._format_context(chunks)

        # Build conversation history block
        history_block = ""
        if history:
            turns = history[-6:]   # last 3 exchanges
            history_block = "CONVERSATION HISTORY\n" + "-" * 20 + "\n"
            for h in turns:
                role = "User" if h.get("role") == "user" else "Assistant"
                history_block += f"{role}: {h.get('content', '')}\n"
            history_block += "\n"

        prompt = (
            f"{history_block}"
            f"TRANSCRIPT EXCERPTS\n"
            f"{'-' * 20}\n"
            f"{context}\n"
            f"QUESTION\n"
            f"{'-' * 20}\n"
            f"{question}"
        )

        return self._call_llm_raw(prompt, system=_CHAT_SYSTEM_PROMPT)

    def pretty_print(self, mom: Dict) -> str:
        lines = ["=" * 60, f"  MINUTES OF MEETING: {mom.get('title', 'Untitled')}", "=" * 60]
        lines += ["\n📋 AGENDA"] + [f"   • {i}" for i in mom.get("agenda", [])]
        lines.append("\n🗝  KEY POINTS")
        for kp in mom.get("key_points", []):
            lines.append(f"   [{kp.get('timestamp','')}] {kp.get('speaker','')}: {kp.get('point','')}")
        lines.append("\n✅ DECISIONS")
        for d in mom.get("decisions", []):
            lines.append(f"   [{d.get('timestamp','')}] {d.get('decision','')}")
        lines.append("\n📌 ACTION ITEMS")
        for a in mom.get("action_items", []):
            lines.append(f"   [{a.get('timestamp','')}] {a.get('owner','Unknown')} → {a.get('task','')}")
        lines += ["\n📝 SUMMARY", f"   {mom.get('summary','')}", "=" * 60]
        return "\n".join(lines)

    # ── Section generation ────────────────────────────────────────

    def _generate_section(self, section: str) -> Dict:
        q1, q2 = _SECTION_QUERIES[section]
        chunks  = self._retrieve_multi([q1, q2], top_k=self.top_k)

        if not chunks:
            chunks = self.store._chunks[:4]   # fallback: first few chunks

        context = self._format_context(chunks)
        prompt  = _SECTION_PROMPTS[section].format(context=context)
        raw     = self._call_llm_raw(prompt, system=_MOM_SYSTEM_PROMPT)
        return self._parse_json(raw)

    # ── Retrieval ─────────────────────────────────────────────────

    def _retrieve_multi(self, queries: List[str], top_k: int) -> List[Dict]:
        """Run multiple queries, merge results, deduplicate by chunk_id."""
        seen:   set  = set()
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

    def _expand_chat_query(self, question: str) -> List[str]:
        """
        Return 2–3 query variants for better retrieval coverage.
        Simple rule-based expansion — no LLM call needed.
        """
        q = question.strip()
        variants = [q]

        # Add keyword-focused variant by stripping question words
        keyword_q = re.sub(
            r"^(what|who|when|where|how|did|was|were|is|are|can|could|tell me about|"
            r"summarize|summarise|explain|describe)\s+", "", q, flags=re.IGNORECASE
        ).strip("?. ")
        if keyword_q and keyword_q.lower() != q.lower():
            variants.append(keyword_q)

        # Add action-oriented variant for "who should / needs to" questions
        if any(w in q.lower() for w in ["who", "action", "task", "responsible", "owner", "assigned"]):
            variants.append("action items tasks responsibilities assigned owner")

        return variants[:3]

    def _retrieve(self, query: str) -> List[Dict]:
        results = self.store.search(query, top_k=self.top_k)
        return [r for r in results if r.get("score", 0) >= self.score_threshold]

    def _format_context(self, chunks: List[Dict]) -> str:
        """Format retrieved chunks as numbered, timestamped context for the LLM."""
        lines = []
        for i, chunk in enumerate(sorted(chunks, key=lambda c: c["start"]), 1):
            ts       = f"[{chunk['start_timestamp']} - {chunk['end_timestamp']}]"
            speakers = chunk.get("speakers", [])
            sp       = f" ({', '.join(speakers)})" if speakers else ""
            lines.append(f"Excerpt {i} {ts}{sp}:\n{chunk['raw_text'].strip()}\n")
        return "\n".join(lines)

    # ── LLM calls ─────────────────────────────────────────────────

    def _call_llm_raw(self, prompt: str, system: Optional[str] = None) -> str:
        """Send a prompt to the configured LLM backend and return raw text."""
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
            print("  ↓ Using template fallback...")
            return self._template_fallback(prompt)

    def _call_openrouter(self, prompt: str, system: str) -> str:
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("Run: pip install openai")
        if self._client is None:
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        model = self.model or "arcee-ai/trinity-large-preview:free"
        response = self._client.chat.completions.create(
            model=model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt},
            ],
            extra_headers={
                "HTTP-Referer": "https://github.com/meeting-intelligence-platform",
                "X-Title":      "Meeting Intelligence Platform",
            },
        )
        return response.choices[0].message.content.strip()

    def _call_anthropic(self, prompt: str, system: str) -> str:
        try:
            import anthropic
        except ImportError:
            raise ImportError("Run: pip install anthropic")
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
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("Run: pip install openai")
        if self._client is None:
            self._client = OpenAI(api_key=self.api_key)
        model = self.model or "gpt-3.5-turbo"
        response = self._client.chat.completions.create(
            model=model,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt},
            ],
        )
        return response.choices[0].message.content.strip()

    # ── JSON parsing ──────────────────────────────────────────────

    def _parse_json(self, raw: str) -> Dict:
        """
        Robustly parse JSON from LLM output.
        Handles: markdown fences, trailing commas, BOM, leading text before '{'.
        """
        # Strip markdown fences
        cleaned = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()

        # Strip BOM / zero-width chars
        cleaned = cleaned.lstrip("\ufeff\u200b")

        # If the LLM prefixed with prose, find the first '{' or '['
        brace = cleaned.find("{")
        bracket = cleaned.find("[")
        start = -1
        if brace != -1 and (bracket == -1 or brace < bracket):
            start = brace
        elif bracket != -1:
            start = bracket
        if start > 0:
            cleaned = cleaned[start:]

        # Fix trailing commas before ] or } (common LLM quirk)
        cleaned = re.sub(r",\s*([\]\}])", r"\1", cleaned)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            print(f"    ⚠ JSON parse failed: {e} — raw snippet: {cleaned[:120]!r}")
            return {}

    # ── Template fallback ─────────────────────────────────────────

    def _template_fallback(self, prompt: str) -> str:
        """Minimal rule-based fallback when the LLM is unavailable."""
        p = prompt.lower()
        if '"agenda"' in p or "main topics" in p:
            return json.dumps({"agenda": ["General discussion", "Planning", "Next steps"]})
        if "key_points" in p or "important statements" in p:
            return json.dumps({"key_points": []})
        if '"decisions"' in p or "decisions" in p:
            return json.dumps({"decisions": []})
        if "action_items" in p or "action items" in p:
            return json.dumps({"action_items": []})
        if '"title"' in p or "descriptive title" in p:
            return json.dumps({"title": "Meeting Minutes"})
        return json.dumps({"summary": "Meeting summary not available — LLM backend unreachable."})
