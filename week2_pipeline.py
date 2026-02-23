"""
Week 2 Pipeline — Semantic Understanding & MoM Generation

Usage:
    # Template MoM (no API key needed)
    python week2_pipeline.py data/transcripts/ES2002a.Mix-Headset.json

    # With Anthropic Claude (best quality)
    python week2_pipeline.py data/transcripts/ES2002a.Mix-Headset.json --backend anthropic --api-key sk-ant-xxx

    # With OpenAI
    python week2_pipeline.py data/transcripts/ES2002a.Mix-Headset.json --backend openai --api-key sk-xxx

    # Search after building
    python week2_pipeline.py data/transcripts/ES2002a.Mix-Headset.json --query "what was decided about the budget"
"""

import sys
import json
from pathlib import Path

from src.chunking.chunker import TranscriptChunker
from src.vector_store.store import MeetingVectorStore
from src.report_generation.mom_generator import MoMGenerator


def run_pipeline(
    transcript_json: str,
    backend: str = "template",
    api_key: str = None,
    query: str = None,
    vector_store_dir: str = None
):
    transcript_path = Path(transcript_json)
    if not transcript_path.exists():
        print(f"✗ Transcript not found: {transcript_json}")
        sys.exit(1)

    meeting_name = transcript_path.stem
    output_dir = Path("data/jobs") / meeting_name
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  Week 2 Pipeline: {meeting_name}")
    print(f"{'='*60}")

    # ── Step 1: Chunk ─────────────────────────────────────────────
    print("\n[1/3] Chunking transcript...")
    chunker = TranscriptChunker(max_chunk_words=120, overlap_segments=1)
    chunks = chunker.chunk_transcript(transcript_json)

    # Save chunks
    chunks_path = output_dir / "chunks.json"
    with open(chunks_path, "w") as f:
        json.dump(chunks, f, indent=2, default=str)
    print(f"  Chunks saved → {chunks_path}")

    # ── Step 2: Embed + Vector Store ──────────────────────────────
    print("\n[2/3] Building vector store...")
    store_dir = vector_store_dir or str(output_dir / "vector_store")
    store = MeetingVectorStore()

    index_exists = (Path(store_dir) / "index.faiss").exists()
    if index_exists:
        print(f"  Found existing index, loading from '{store_dir}'...")
        store.load(store_dir)
        # Pre-warm the model now so search doesn't reload it separately
        store._get_model()
    else:
        store.build(chunks)
        store.save(store_dir)

    # ── Step 3: MoM Generation ────────────────────────────────────
    print("\n[3/3] Generating Minutes of Meeting...")
    mom_path = str(output_dir / "mom.json")
    generator = MoMGenerator(backend=backend, api_key=api_key)
    mom = generator.generate(chunks, output_path=mom_path)

    print()
    print(generator.pretty_print(mom))

    # ── Optional: Semantic Search ─────────────────────────────────
    if query:
        print(f"\n{'='*60}")
        print(f"  Search: \"{query}\"")
        print(f"{'='*60}")
        results = store.search(query, top_k=3)
        for i, r in enumerate(results, 1):
            print(f"\n  Result {i} (score: {r['score']:.3f})")
            print(f"  Time: {r['start_timestamp']} → {r['end_timestamp']}")
            print(f"  Text: {r['raw_text'][:200]}")

    print(f"\n✓ All outputs saved to: {output_dir}/")
    return mom, store


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Week 2 Pipeline - MoM + Vector Store")
    parser.add_argument("transcript", help="Path to Whisper JSON transcript")
    parser.add_argument("--backend", default="template", choices=["template", "anthropic", "openai"],
                        help="LLM backend for MoM generation (default: template)")
    parser.add_argument("--api-key", default=None, help="API key for LLM backend")
    parser.add_argument("--query", default=None, help="Optional semantic search query to test")
    parser.add_argument("--store-dir", default=None, help="Directory to save/load vector store")
    args = parser.parse_args()

    run_pipeline(
        transcript_json=args.transcript,
        backend=args.backend,
        api_key=args.api_key,
        query=args.query,
        vector_store_dir=args.store_dir
    )


if __name__ == "__main__":
    main()
