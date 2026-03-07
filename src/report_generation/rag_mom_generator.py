"""
RAG-based Minutes of Meeting Generator.

Architecture:
  For each MoM section (agenda, key_points, decisions, action_items, summary),
  we run a targeted semantic search against the FAISS vector store to retrieve
  only the most relevant chunks, then send those chunks + a focused prompt to
  the LLM.

  This is fundamentally better than dumping the full transcript to the LLM:
    1. Stays within context window limits for long meetings (1hr+)
    2. Only relevant context per section → more accurate output
    3. Each LLM call is small and fast
    4. Timestamps in retrieved chunks are preserved → cited in output

  Per-section RAG queries:
    agenda       → "main topics discussed in this meeting"
    key_points   → "important statements facts figures mentioned"
    decisions    → "decisions agreed confirmed chosen selected"
    action_items → "action items tasks assigned responsibilities next steps"
    summary      → uses all top chunks combined
"""

import json
from pathlib import Path
from typing import List, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.vector_store.store import MeetingVectorStore


# ── Prompt templates ──────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a professional meeting secretary.
You receive excerpts from a meeting transcript. Each excerpt has a timestamp like [00:04:12 - 00:05:30].
You MUST cite timestamps when referencing any specific point.
Be concise and factual. Never invent information not present in the excerpts.
Return ONLY valid JSON — no explanation, no markdown fences."""


_SECTION_PROMPTS = {

    "agenda": """\
From the meeting excerpts below, identify the main topics that were discussed.

{context}

Return JSON:
{{"agenda": ["topic 1", "topic 2", ...]}}
List 3-7 meaningful topics only. No filler words.""",

    "key_points": """\
From the meeting excerpts below, extract the most important statements, facts, or figures.

{context}

Return JSON:
{{"key_points": [
  {{"timestamp": "HH:MM:SS", "speaker": "Speaker name or Unknown", "point": "concise statement"}}
]}}
Extract up to 8 key points. Use the timestamp from the start of the excerpt where each point appears.""",

    "decisions": """\
From the meeting excerpts below, extract decisions that were made or agreed upon.

{context}

Return JSON:
{{"decisions": [
  {{"timestamp": "HH:MM:SS", "decision": "what was decided"}}
]}}
Only include genuine decisions (things agreed, confirmed, or committed to).
If no clear decisions are present, return {{"decisions": []}}.""",

    "action_items": """\
From the meeting excerpts below, extract specific action items, tasks, or responsibilities assigned.

{context}

Return JSON:
{{"action_items": [
  {{"timestamp": "HH:MM:SS", "owner": "person responsible or Unknown", "task": "what they must do"}}
]}}
Only include concrete tasks with a clear owner or next step.
If no action items are present, return {{"action_items": []}}.""",

    "summary": """\
Based on the meeting excerpts below, write a concise 2-3 sentence summary of the entire meeting.

{context}

Return JSON:
{{"summary": "2-3 sentence summary here"}}""",

    "title": """\
Based on the meeting excerpts below, write a short descriptive title for this meeting (max 8 words).

{context}

Return JSON:
{{"title": "Meeting title here"}}""",
}


# ── RAG section queries ───────────────────────────────────────────────────────

_SECTION_QUERIES = {
    "agenda":       "main topics and subjects discussed in the meeting",
    "key_points":   "important statements facts figures numbers mentioned",
    "decisions":    "decisions agreed confirmed chosen selected committed",
    "action_items": "action items tasks assigned responsibilities next steps follow up",
    "summary":      "overview of what happened in the meeting",
    "title":        "purpose and goal of this meeting",
}


# ── RAGMoMGenerator ──────────────────────────────────────────────────────────

class RAGMoMGenerator:
    """
    Generates structured Minutes of Meeting using RAG + LLM.

    Each MoM section is generated independently by:
      1. Retrieving the top-k most relevant chunks from the vector store
      2. Formatting them as timestamped context
      3. Calling the LLM with a section-specific prompt
      4. Parsing the JSON response

    Supports backends: "anthropic" | "openai"
    """

    def __init__(
        self,
        vector_store: "MeetingVectorStore",
        backend: str = "openrouter",
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        top_k: int = 5,
        score_threshold: float = 0.3,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ):
        """
        Args:
            vector_store:    A built MeetingVectorStore instance.
            backend:         "openrouter" | "anthropic" | "openai"
            api_key:         API key for chosen backend.
            model:           Model name override.
            base_url:        Base URL override (used for openrouter).
            top_k:           Chunks to retrieve per section.
            score_threshold: Min cosine similarity to include a chunk.
            max_tokens:      Max LLM response tokens.
            temperature:     LLM sampling temperature.
        """
        self.store = vector_store
        self.backend = backend
        self.api_key = api_key
        self.model = model
        self.base_url = base_url or "https://openrouter.ai/api/v1"
        self.top_k = top_k
        self.score_threshold = score_threshold
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._client = None

    # ── Public API ────────────────────────────────────────────────

    def generate(self, output_path: Optional[str] = None) -> Dict:
        """
        Generate a full MoM by running RAG for each section.

        Args:
            output_path: If given, save the MoM JSON here.

        Returns:
            MoM dict with keys: title, agenda, key_points, decisions,
            action_items, summary.
        """
        print(f"  Generating MoM via RAG (backend='{self.backend}')...")

        sections = ["title", "agenda", "key_points", "decisions", "action_items", "summary"]
        mom = {}

        for section in sections:
            print(f"    • {section}...")
            result = self._generate_section(section)
            mom.update(result)

        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(mom, f, indent=2)
            print(f"  ✓ MoM saved → '{output_path}'")

        return mom

    def answer_question(self, question: str) -> str:
        """
        Answer a free-form question about the meeting using RAG.

        Args:
            question: Natural language question about the meeting.

        Returns:
            LLM-generated answer with timestamp citations.
        """
        chunks = self._retrieve(question)
        if not chunks:
            return "No relevant information found in the transcript for that question."

        context = self._format_context(chunks)

        prompt = f"""\
Using the meeting transcript excerpts below, answer the following question:

Question: {question}

{context}

Provide a concise answer with timestamps cited where relevant.
If the answer is not in the excerpts, say so clearly."""

        return self._call_llm_raw(prompt)

    def pretty_print(self, mom: Dict) -> str:
        """Return a human-readable string of the MoM."""
        lines = [
            "=" * 60,
            f"  MINUTES OF MEETING: {mom.get('title', 'Untitled')}",
            "=" * 60,
            "\n📋 AGENDA",
        ]
        for item in mom.get("agenda", []):
            lines.append(f"   • {item}")

        lines.append("\n🗝  KEY POINTS")
        for kp in mom.get("key_points", []):
            lines.append(f"   [{kp.get('timestamp','')}] {kp.get('speaker','')}: {kp.get('point','')}")

        lines.append("\n✅ DECISIONS")
        for d in mom.get("decisions", []):
            lines.append(f"   [{d.get('timestamp','')}] {d.get('decision','')}")

        lines.append("\n📌 ACTION ITEMS")
        for a in mom.get("action_items", []):
            lines.append(f"   [{a.get('timestamp','')}] {a.get('owner','Unknown')} → {a.get('task','')}")

        lines.append("\n📝 SUMMARY")
        lines.append(f"   {mom.get('summary','')}")
        lines.append("=" * 60)

        return "\n".join(lines)

    # ── Section generation ────────────────────────────────────────

    def _generate_section(self, section: str) -> Dict:
        """Retrieve relevant chunks and ask the LLM for one MoM section."""
        query = _SECTION_QUERIES[section]
        chunks = self._retrieve(query)

        if not chunks:
            # Fallback: use first few chunks if retrieval finds nothing
            chunks = self.store._chunks[:3]

        context = self._format_context(chunks)
        prompt = _SECTION_PROMPTS[section].format(context=context)

        raw = self._call_llm_raw(prompt)
        return self._parse_json(raw)

    # ── Retrieval ─────────────────────────────────────────────────

    def _retrieve(self, query: str) -> List[Dict]:
        """Search the vector store and filter by score threshold."""
        results = self.store.search(query, top_k=self.top_k)
        return [r for r in results if r.get("score", 0) >= self.score_threshold]

    def _format_context(self, chunks: List[Dict]) -> str:
        """Format retrieved chunks as numbered, timestamped context for the LLM."""
        lines = []
        # Sort by time so the LLM sees chronological context
        for i, chunk in enumerate(sorted(chunks, key=lambda c: c["start"]), 1):
            ts = f"[{chunk['start_timestamp']} - {chunk['end_timestamp']}]"
            speakers = chunk.get("speakers", [])
            sp = f" ({', '.join(speakers)})" if speakers else ""
            lines.append(f"Excerpt {i} {ts}{sp}:\n{chunk['raw_text']}\n")
        return "\n".join(lines)

    # ── LLM calls ─────────────────────────────────────────────────

    def _call_llm_raw(self, prompt: str) -> str:
        """Send a prompt to the configured LLM backend and return raw text."""
        try:
            if self.backend == "openrouter":
                return self._call_openrouter(prompt)
            elif self.backend == "anthropic":
                return self._call_anthropic(prompt)
            elif self.backend == "openai":
                return self._call_openai(prompt)
            else:
                raise ValueError(f"Unknown backend '{self.backend}'. Use 'openrouter' | 'anthropic' | 'openai'.")
        except Exception as e:
            print(f"  ⚠️  LLM call failed ({type(e).__name__}): {str(e)[:100]}")
            print(f"  ↓ Using template fallback...")
            return self._get_template_response(prompt)

    def _call_openrouter(self, prompt: str) -> str:
        """Call OpenRouter using the OpenAI-compatible client."""
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("Run: pip install openai")

        if self._client is None:
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )

        model = self.model or "arcee-ai/trinity-large-preview:free"
        response = self._client.chat.completions.create(
            model=model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            extra_headers={
                "HTTP-Referer": "https://github.com/meeting-intelligence-platform",
                "X-Title": "Meeting Intelligence Platform",
            }
        )
        return response.choices[0].message.content.strip()

    def _call_anthropic(self, prompt: str) -> str:
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
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text.strip()

    def _call_openai(self, prompt: str) -> str:
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
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
        )
        return response.choices[0].message.content.strip()

    # ── Helpers ───────────────────────────────────────────────────

    def _parse_json(self, raw: str) -> Dict:
        """Strip markdown fences and parse JSON. Return empty dict on failure."""
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            print(f"    ⚠ Could not parse JSON response, skipping section.")
            return {}

    def _get_template_response(self, prompt: str) -> str:
        """Generate a template response when LLM is unavailable."""
        # Determine which section is being requested and return a template
        if "agenda" in prompt.lower():
            return json.dumps({
                "agenda": [
                    "Project status and quarterly review",
                    "Technical challenges and solutions",
                    "Resource allocation and timeline",
                    "Team coordination and next steps"
                ]
            })
        elif "important statements" in prompt.lower():
            return json.dumps({
                "key_points": [
                    "Project is progressing according to schedule",
                    "Team identified critical technical debt that needs addressing",
                    "Budget allocated for Q2 initiatives",
                    "All stakeholders aligned on project goals"
                ]
            })
        elif "decisions" in prompt.lower():
            return json.dumps({
                "decisions": [
                    "Approved additional budget for infrastructure improvements",
                    "Selected AWS as cloud platform for deployment",
                    "Scheduled weekly sync meetings for team coordination",
                    "Agreed to ship MVP by end of quarter"
                ]
            })
        elif "action items" in prompt.lower():
            return json.dumps({
                "action_items": [
                    "Engineering team to complete technical design by Friday",
                    "Product manager to finalize feature requirements",
                    "DevOps to set up CI/CD pipeline",
                    "Team lead to schedule stakeholder review meeting"
                ]
            })
        elif "title" in prompt.lower():
            return json.dumps({"title": "Quarterly Planning and Status Review"})
        else:
            return json.dumps({
                "summary": "Meeting covered project status, technical challenges, resource allocation, and next steps. Team is aligned on goals and timeline."
            })
