import json
import pickle
from pathlib import Path
from typing import List, Dict, Optional

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer


class MeetingVectorStore:
    """
    Embeds meeting transcript chunks and stores them in a FAISS index
    for fast semantic search.

    Uses the `embedded_text` field from each chunk (which includes
    speaker + timestamp metadata) so queries resolve even when chunks
    only contain pronouns or implicit references.
    """

    DEFAULT_MODEL = "all-MiniLM-L6-v2"   # 384-dim, fast, good quality

    def __init__(self, model_name: str = DEFAULT_MODEL):
        """
        Args:
            model_name: SentenceTransformer model to use for embeddings.
        """
        self.model_name = model_name
        self._model: Optional[SentenceTransformer] = None
        self._index: Optional[faiss.IndexFlatL2] = None
        self._chunks: List[Dict] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self, chunks: List[Dict]) -> None:
        """
        Embed all chunks and build the FAISS index.

        Args:
            chunks: List of chunk dicts from TranscriptChunker.
        """
        if not chunks:
            raise ValueError("Cannot build index from empty chunk list.")

        print(f"  Loading embedding model '{self.model_name}'...")
        model = self._get_model()

        texts = [c["embedded_text"] for c in chunks]
        print(f"  Embedding {len(texts)} chunks...")
        embeddings = model.encode(texts, show_progress_bar=True, convert_to_numpy=True)
        embeddings = embeddings.astype("float32")

        # Normalise for cosine similarity via L2 on unit vectors
        faiss.normalize_L2(embeddings)

        dim = embeddings.shape[1]
        self._index = faiss.IndexFlatIP(dim)   # Inner product == cosine after normalisation
        self._index.add(embeddings)
        self._chunks = chunks

        print(f"  ✓ FAISS index built — {self._index.ntotal} vectors, dim={dim}")

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        Semantic search over the indexed chunks.

        Args:
            query:  Natural language query.
            top_k:  Number of results to return.

        Returns:
            List of chunk dicts sorted by relevance, each with an added
            'score' field (cosine similarity, higher = better).
        """
        if self._index is None or not self._chunks:
            raise RuntimeError("Index is empty. Call build() first.")

        model = self._get_model()
        q_vec = model.encode([query], convert_to_numpy=True).astype("float32")
        faiss.normalize_L2(q_vec)

        scores, indices = self._index.search(q_vec, min(top_k, len(self._chunks)))

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            chunk = dict(self._chunks[idx])
            chunk["score"] = float(score)
            results.append(chunk)

        return results

    def save(self, directory: str) -> None:
        """
        Persist the FAISS index and chunk metadata to disk.

        Args:
            directory: Folder to save index files into.
        """
        if self._index is None:
            raise RuntimeError("Nothing to save. Call build() first.")

        out = Path(directory)
        out.mkdir(parents=True, exist_ok=True)

        faiss.write_index(self._index, str(out / "index.faiss"))

        with open(out / "chunks.pkl", "wb") as f:
            pickle.dump(self._chunks, f)

        with open(out / "meta.json", "w") as f:
            json.dump({"model_name": self.model_name, "num_chunks": len(self._chunks)}, f, indent=2)

        print(f"  ✓ Vector store saved to '{directory}'")

    def load(self, directory: str) -> None:
        """
        Load a previously saved FAISS index and chunk metadata.

        Args:
            directory: Folder containing saved index files.
        """
        d = Path(directory)
        index_path = d / "index.faiss"
        chunks_path = d / "chunks.pkl"

        if not index_path.exists() or not chunks_path.exists():
            raise FileNotFoundError(f"No saved index found in '{directory}'")

        self._index = faiss.read_index(str(index_path))

        with open(chunks_path, "rb") as f:
            self._chunks = pickle.load(f)

        with open(d / "meta.json") as f:
            meta = json.load(f)
            self.model_name = meta.get("model_name", self.model_name)

        print(f"  ✓ Loaded vector store — {self._index.ntotal} vectors from '{directory}'")

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(self.model_name)
        return self._model


# ------------------------------------------------------------------
# Convenience functions
# ------------------------------------------------------------------

def build_vector_store(chunks: List[Dict], save_dir: Optional[str] = None) -> MeetingVectorStore:
    """
    Build a vector store from transcript chunks and optionally save it.

    Args:
        chunks:   Output of TranscriptChunker.chunk_transcript().
        save_dir: If provided, persist the index to this directory.

    Returns:
        A ready-to-search MeetingVectorStore instance.
    """
    store = MeetingVectorStore()
    store.build(chunks)
    if save_dir:
        store.save(save_dir)
    return store


def load_vector_store(directory: str) -> MeetingVectorStore:
    """
    Load a previously saved vector store.

    Args:
        directory: Folder containing saved index files.

    Returns:
        A ready-to-search MeetingVectorStore instance.
    """
    store = MeetingVectorStore()
    store.load(directory)
    return store
