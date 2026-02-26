"""
Week 2 Pipeline — Semantic Understanding & MoM Generation (RAG edition)

All settings come from config.py / .env — no hardcoded values.

Usage:
    # Template fallback (no API key)
    python week2_pipeline.py data/transcripts/ES2002a.Mix-Headset.json

    # RAG + Claude (set LLM_BACKEND=anthropic + ANTHROPIC_API_KEY in .env)
    python week2_pipeline.py data/transcripts/ES2002a.Mix-Headset.json

    # Override backend from CLI
    python week2_pipeline.py data/transcripts/ES2002a.Mix-Headset.json --backend anthropic

    # Ask a question about the meeting
    python week2_pipeline.py data/transcripts/ES2002a.Mix-Headset.json \\
        --query "what did they decide about the remote control design"

    # Force rebuild of vector store (ignore cache)
    python week2_pipeline.py data/transcripts/ES2002a.Mix-Headset.json --rebuild
"""

import sys
import json
import argparse
from pathlib import Path

from config import settings
from src.chunking.chunker import TranscriptChunker
from src.vector_store.store import MeetingVectorStore


def run_pipeline(
    transcript_json: str,
    backend: str = None,
    query: str = None,
    rebuild: bool = False,
):
    transcript_path = Path(transcript_json)
    if not transcript_path.exists():
        print(f"✗ Transcript not found: {transcript_json}")
        sys.exit(1)

    # Use CLI override or fall back to config
    active_backend = backend or settings.llm_backend
    meeting_name = transcript_path.stem
    job_dir = settings.job_dir(meeting_name)
    job_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  Week 2 Pipeline: {meeting_name}")
    print(f"  Backend: {active_backend}  |  Embedding: {settings.embedding_model}")
    print(f"{'='*60}")

    # ── Step 1: Chunk ─────────────────────────────────────────────
    print("\n[1/3] Chunking transcript...")
    chunker = TranscriptChunker(
        max_chunk_words=settings.chunk_max_words,
        overlap_segments=settings.chunk_overlap_segments,
    )
    chunks = chunker.chunk_transcript(transcript_json)

    chunks_path = job_dir / "chunks.json"
    with open(chunks_path, "w") as f:
        json.dump(chunks, f, indent=2, default=str)
    print(f"  Chunks saved → {chunks_path}")

    # ── Step 2: Vector Store ──────────────────────────────────────
    print("\n[2/3] Building vector store...")
    store_dir = str(job_dir / "vector_store")
    store = MeetingVectorStore(model_name=settings.embedding_model)

    index_exists = (Path(store_dir) / "index.faiss").exists()
    if index_exists and not rebuild:
        print(f"  Found existing index, loading from '{store_dir}'...")
        store.load(store_dir)
        store._get_model()   # pre-warm so search reuses the same model instance
    else:
        if rebuild and index_exists:
            print("  --rebuild flag set, rebuilding index...")
        store.build(chunks)
        store.save(store_dir)

    # ── Step 3: MoM Generation ────────────────────────────────────
    print("\n[3/3] Generating Minutes of Meeting...")
    mom_path = str(job_dir / "mom.json")

    if active_backend == "template":
        # Lightweight fallback — no LLM required
        from src.report_generation.mom_generator import MoMGenerator
        generator = MoMGenerator(backend="template")
        mom = generator.generate(chunks, output_path=mom_path)
        print()
        print(generator.pretty_print(mom))

    else:
        # RAG + LLM
        api_key_map = {
            "anthropic":  settings.anthropic_api_key,
            "openai":     settings.openai_api_key,
            "openrouter": settings.openrouter_api_key,
        }
        env_var_map = {
            "anthropic":  "ANTHROPIC_API_KEY",
            "openai":     "OPENAI_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
        }

        if active_backend not in api_key_map:
            print(f"✗ Unknown backend '{active_backend}'. Use: openrouter | anthropic | openai | template")
            sys.exit(1)

        api_key = api_key_map[active_backend]
        if not api_key:
            print(f"✗ No API key found for backend '{active_backend}'.")
            print(f"  Set {env_var_map[active_backend]} in your .env file.")
            sys.exit(1)

        from src.report_generation.rag_mom_generator import RAGMoMGenerator
        rag = RAGMoMGenerator(
            vector_store=store,
            backend=active_backend,
            api_key=api_key,
            model=settings.get_llm_model(),
            base_url=settings.openrouter_base_url if active_backend == "openrouter" else None,
            top_k=settings.rag_top_k,
            score_threshold=settings.rag_score_threshold,
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
        )
        mom = rag.generate(output_path=mom_path)
        print()
        print(rag.pretty_print(mom))

        # ── Optional: free-form Q&A ────────────────────────────────
        if query:
            print(f"\n{'='*60}")
            print(f"  Q: {query}")
            print(f"{'='*60}")
            answer = rag.answer_question(query)
            print(f"\n  A: {answer}")

    # ── If template + query, fall back to raw vector search ──────
    if active_backend == "template" and query:
        print(f"\n{'='*60}")
        print(f"  Search: \"{query}\"")
        print(f"{'='*60}")
        results = store.search(query, top_k=3)
        for i, r in enumerate(results, 1):
            print(f"\n  Result {i}  (score: {r['score']:.3f})")
            print(f"  Time : {r['start_timestamp']} → {r['end_timestamp']}")
            print(f"  Text : {r['raw_text'][:200]}")

    print(f"\n✓ All outputs saved to: {job_dir}/")
    return mom, store


def main():
    parser = argparse.ArgumentParser(description="Week 2 Pipeline — MoM + RAG")
    parser.add_argument("transcript", help="Path to Whisper JSON transcript")
    parser.add_argument(
        "--backend", default=None,
        choices=["template", "anthropic", "openai", "openrouter"],
        help="LLM backend override (default: from .env LLM_BACKEND)"
    )
    parser.add_argument("--query", default=None, help="Question to answer about the meeting")
    parser.add_argument("--rebuild", action="store_true", help="Force rebuild of vector store cache")
    args = parser.parse_args()

    run_pipeline(
        transcript_json=args.transcript,
        backend=args.backend,
        query=args.query,
        rebuild=args.rebuild,
    )


if __name__ == "__main__":
    main()
