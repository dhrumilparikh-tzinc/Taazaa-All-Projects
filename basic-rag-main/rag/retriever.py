from typing import List, Dict, Any, Tuple, Optional

import numpy as np

from rag.embedder import Embedder
from rag.faiss_store import (
    load_faiss_index,
    load_metadata,
    search_index,
)


# Lazy globals so we don't reload on every call
_index = None
_metadata: List[Dict[str, Any]] = []
_embedder: Optional[Embedder] = None


def _ensure_loaded():
    global _index, _metadata, _embedder
    if _index is None:
        _index = load_faiss_index()
    if not _metadata:
        _metadata = load_metadata()
    if _embedder is None:
        _embedder = Embedder()


def retrieve(question: str, k: int = 5) -> List[Dict[str, Any]]:
    """
    Given a question string, returns a list of dicts:
    [{"text": chunk_text, "distance": dist, "chunk_id": id}, ...]
    """
    _ensure_loaded()

    query_vec: np.ndarray = _embedder.embed_query(question)  # shape (1, dim)
    distances, indices = search_index(_index, query_vec, k=k)

    results: List[Dict[str, Any]] = []
    for dist, idx in zip(distances[0], indices[0]):
        if idx == -1:
            continue
        meta = _metadata[idx]
        results.append(
            {
                "chunk_id": meta.get("chunk_id", idx),
                "text": meta["text"],
                "distance": float(dist),
                "doc_id": meta.get("doc_id"),
                "chunk_in_doc": meta.get("chunk_in_doc"),
                "metadata": meta.get("metadata", {}),
            }
        )
    return results


if __name__ == "__main__":
    query = "What are the symptoms of diabetes?"  # adjust to your dataset
    hits = retrieve(query, k=3)
    print("Query:", query)
    for i, hit in enumerate(hits, start=1):
        print(f"\nTop {i} (distance={hit['distance']:.4f}):")
        print(hit["text"][:500])
