"""
Text embedding via Gemini text-embedding-004 (768-dim vectors).

All embedding calls go through the Google Gemini API — no local ONNX model,
no fastembed, no sentence-transformers.

embed_chunks() — batch-embeds a list of chunk dicts using task_type=
                 "retrieval_document"; logs latency to UsageLog.
embed_query()  — single-vector embed for RAG queries using task_type=
                 "retrieval_query" for better asymmetric retrieval quality.

Both functions retry up to 3 times with exponential back-off on rate-limit
errors so transient quota exhaustion doesn't fail a document upload.
"""

import time

from app.observability.logging import get_logger, log_llm_call

log = get_logger()


def _embed_texts(texts: list[str], settings, task_type: str) -> list[list[float]]:
    """Call Gemini embed_content for a list of texts. Returns list of float vectors."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    vectors = []

    for text in texts:
        for attempt in range(4):
            try:
                resp = client.models.embed_content(
                    model=settings.GEMINI_EMBEDDING_MODEL,
                    contents=text,
                    config=types.EmbedContentConfig(task_type=task_type),
                )
                vectors.append(list(resp.embeddings[0].values))
                break
            except Exception as e:
                msg = str(e).lower()
                if ("429" in msg or "rate" in msg or "quota" in msg) and attempt < 3:
                    wait = 15 * (attempt + 1)
                    log.warning("embed_rate_limit_retry", attempt=attempt, wait_s=wait)
                    time.sleep(wait)
                    continue
                raise
        else:
            raise RuntimeError(f"embed_texts: exhausted retries for task_type={task_type}")

    return vectors


def embed_chunks(
    chunks: list[dict],
    user_id,
    job_id,
    settings,
    db,
) -> list[list[float]]:
    """Embed document chunks for indexing. Returns parallel list of 768-dim vectors."""
    texts = [c["text"] for c in chunks]
    start = time.time()

    vectors = _embed_texts(texts, settings, task_type="retrieval_document")

    latency_ms = int((time.time() - start) * 1000)
    log.info(
        "embed_batch_done",
        batch_size=len(texts),
        dimensions=len(vectors[0]) if vectors else 0,
        latency_ms=latency_ms,
        model=settings.GEMINI_EMBEDDING_MODEL,
    )
    log_llm_call(
        user_id=user_id,
        job_id=job_id,
        endpoint="embed_chunks",
        model=settings.GEMINI_EMBEDDING_MODEL,
        prompt_tokens=len(" ".join(texts).split()),
        completion_tokens=0,
        latency_ms=latency_ms,
        db=db,
    )
    return vectors


def embed_query(question: str, settings) -> list[float]:
    """Embed a single query string for vector search. Returns 768-dim vector."""
    vectors = _embed_texts([question], settings, task_type="retrieval_query")
    return vectors[0]
