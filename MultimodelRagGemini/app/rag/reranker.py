"""
Reranker — passthrough stub.

sentence-transformers cross-encoder has been removed in the Gemini-only
re-architecture.  The RAG pipeline uses pure vector similarity from Gemini
text-embedding-004 (768-dim cosine), which is sufficient without a reranker.

rerank() returns the top-k chunks ordered by their existing vector score so
the rest of the pipeline is unaffected.
"""

from app.observability.logging import get_logger

log = get_logger()


def start_bg_load():
    pass


def rerank(question: str, chunks: list[dict], top_k: int) -> list[dict]:
    log.info("reranker_passthrough", top_k=top_k)
    return chunks[:top_k]
