"""
FAISS-backed vector store for Meeting Intelligence Platform.

Metadata schema stored per chunk (in-memory alongside the index):
    chunk_id        : int     — sequential chunk index
    start           : float   — start time in seconds
    end             : float   — end time in seconds
    start_timestamp : str     — "HH:MM:SS" (for display + video clipping)
    end_timestamp   : str     — "HH:MM:SS"
    speakers        : list    — speaker labels present in this chunk
    primary_speaker : str     — first/dominant speaker (for filtering)
    meeting_id      : str     — job/meeting identifier
    word_count      : int     — approximate word count of chunk
    duration        : float   — end - start in seconds
    raw_text        : str     — plain transcript text

The document embedded into FAISS is `embedded_text` (metadata-prefixed text),
which injects speaker+time context into the vector so queries like
"what did Speaker 1 say about budget?" resolve correctly even when chunks
only contain pronouns.

Persistence layout (save_dir/):
    index.faiss   — FAISS IndexFlatIP (cosine via L2-normalised vectors)
    chunks.pkl    — pickled list of chunk dicts
    meta.json     — {model_name, num_chunks, meeting_id}
"""

import json
import pickle
import warnings
from pathlib import Path
from typing import Dict, List, Optional

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

# Suppress noisy FAISS / sentence-transformers deprecation warnings
warnings.filterwarnings("ignore", category=FutureWarning, module="transformers")
warnings.filterwarnings("ignore", category=UserWarning, module="faiss")


class MeetingVectorStore:
    """
    Embeds meeting transcript chunks and stores them in a FAISS index
    for fast semantic search with rich metadata support.

    Supports post-hoc filtering by speaker and time range — critical for
    the video clipping pipeline (map a query → exact clip window).
    """

    DEFAULT_MODEL = "all-MiniLM-L6-v2"   # 384-dim, fast, good quality

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model_name = model_name
        self._model: Optional[SentenceTransformer] = None
        self._index: Optional[faiss.IndexFlatIP] = None
        self._chunks: List[Dict] = []
        self._meeting_id: Optional[str] = None

    # ── Public API ─────────────────────────────────────────────────────────

    def build(self, chunks: List[Dict], meeting_id: Optional[str] = None) -> None:
        """
        Embed all chunks and build the FAISS index.

        Args:
            chunks:     List of chunk dicts from TranscriptChunker.
            meeting_id: Identifier for this meeting (stored in metadata).
        """
        if not chunks:
            raise ValueError("Cannot build index from empty chunk list.")

        self._meeting_id = meeting_id
        self._chunks = [self._enrich_chunk(c, meeting_id) for c in chunks]

        print(f"  Loading embedding model '{self.model_name}'...")
        model = self._get_model()

        texts = [c["embedded_text"] for c in self._chunks]
        print(f"  Embedding {len(texts)} chunks...")
        embeddings = model.encode(texts, show_progress_bar=True, convert_to_numpy=True)
        embeddings = embeddings.astype("float32")

        # Normalise → cosine similarity via inner product on unit vectors
        faiss.normalize_L2(embeddings)

        dim = embeddings.shape[1]
        self._index = faiss.IndexFlatIP(dim)
        self._index.add(embeddings)

        print(f"  ✓ FAISS index built — {self._index.ntotal} vectors, dim={dim}")

    def search(
        self,
        query: str,
        top_k: int = 5,
        speaker_filter: Optional[str] = None,
        start_after: Optional[float] = None,
        end_before: Optional[float] = None,
    ) -> List[Dict]:
        """
        Semantic search over indexed chunks.

        Args:
            query:          Natural language query.
            top_k:          Max number of results to return.
            speaker_filter: Only return chunks where primary_speaker matches.
            start_after:    Only return chunks starting after this time (seconds).
            end_before:     Only return chunks ending before this time (seconds).

        Returns:
            List of chunk dicts sorted by relevance, each with a 'score' field
            (cosine similarity, 1.0 = identical, higher = better).
        """
        if self._index is None or not self._chunks:
            raise RuntimeError("Index is empty. Call build() or load() first.")

        model = self._get_model()
        q_vec = model.encode([query], convert_to_numpy=True).astype("float32")
        faiss.normalize_L2(q_vec)

        # Over-fetch so we have room to apply metadata filters
        fetch_k = min(len(self._chunks), max(top_k * 4, top_k + 20))
        scores, indices = self._index.search(q_vec, fetch_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            chunk = dict(self._chunks[idx])
            chunk["score"] = float(score)

            # Apply optional metadata filters
            if speaker_filter and chunk.get("primary_speaker") != speaker_filter:
                if speaker_filter not in chunk.get("speakers", []):
                    continue
            if start_after is not None and chunk["start"] < start_after:
                continue
            if end_before is not None and chunk["end"] > end_before:
                continue

            results.append(chunk)
            if len(results) >= top_k:
                break

        return results

    def save(self, directory: str, meeting_id: Optional[str] = None) -> None:
        """
        Persist the FAISS index and chunk metadata to disk.

        Args:
            directory:  Folder to write index files into.
            meeting_id: Override meeting ID to store in meta.json.
        """
        if self._index is None:
            raise RuntimeError("Nothing to save. Call build() first.")

        mid = meeting_id or self._meeting_id
        out = Path(directory)
        out.mkdir(parents=True, exist_ok=True)

        faiss.write_index(self._index, str(out / "index.faiss"))

        with open(out / "chunks.pkl", "wb") as f:
            pickle.dump(self._chunks, f)

        with open(out / "meta.json", "w") as f:
            json.dump(
                {
                    "model_name": self.model_name,
                    "num_chunks": len(self._chunks),
                    "meeting_id": mid,
                },
                f,
                indent=2,
            )

        print(f"  ✓ FAISS store saved → '{directory}' ({len(self._chunks)} chunks)")

    def load(self, directory: str, meeting_id: Optional[str] = None) -> None:
        """
        Load a previously saved FAISS index and chunk metadata from disk.

        Args:
            directory:  Folder containing saved index files.
            meeting_id: Optional override (otherwise read from meta.json).
        """
        d = Path(directory)
        index_path = d / "index.faiss"
        chunks_path = d / "chunks.pkl"

        if not index_path.exists() or not chunks_path.exists():
            raise FileNotFoundError(f"No saved FAISS index found in '{directory}'")

        self._index = faiss.read_index(str(index_path))

        with open(chunks_path, "rb") as f:
            self._chunks = pickle.load(f)

        meta_path = d / "meta.json"
        if meta_path.exists():
            with open(meta_path) as f:
                meta = json.load(f)
            self.model_name = meta.get("model_name", self.model_name)
            self._meeting_id = meeting_id or meta.get("meeting_id")

        print(f"  ✓ FAISS store loaded — {self._index.ntotal} vectors from '{directory}'")

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    # ── Internal helpers ──────────────────────────────────────────────────

    def _get_model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def _enrich_chunk(self, chunk: Dict, meeting_id: Optional[str]) -> Dict:
        """Add derived metadata fields to a chunk dict (non-destructive copy)."""
        c = dict(chunk)
        speakers = c.get("speakers", [])
        c.setdefault("primary_speaker", speakers[0] if speakers else "Unknown")
        c.setdefault("meeting_id", meeting_id or "")
        c.setdefault("word_count", len(c.get("raw_text", "").split()))
        c.setdefault("duration", float(c.get("end", 0) - c.get("start", 0)))
        return c


# ── Convenience functions ─────────────────────────────────────────────────────

def build_vector_store(
    chunks: List[Dict],
    save_dir: Optional[str] = None,
    meeting_id: Optional[str] = None,
    model_name: str = MeetingVectorStore.DEFAULT_MODEL,
) -> "MeetingVectorStore":
    """Build a FAISS vector store from transcript chunks and optionally persist it."""
    store = MeetingVectorStore(model_name=model_name)
    store.build(chunks, meeting_id=meeting_id)
    if save_dir:
        store.save(save_dir, meeting_id=meeting_id)
    return store


def load_vector_store(
    directory: str,
    meeting_id: Optional[str] = None,
    model_name: str = MeetingVectorStore.DEFAULT_MODEL,
) -> "MeetingVectorStore":
    """Load a previously saved FAISS vector store from disk."""
    store = MeetingVectorStore(model_name=model_name)
    store.load(directory, meeting_id=meeting_id)
    return store
