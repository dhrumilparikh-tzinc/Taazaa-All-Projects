"""
Core RAG query engine — Gemini-only.

Public API
----------
query(question, job_ids, user_id, db, settings) -> dict
    Full RAG pipeline: query expansion -> embed -> multi-variant vector search ->
    Gemini reranking -> confidence gate -> Gemini LLM -> save QueryHistory.
    Returns answer text, numbered citations, token counts, and latency.

Search Pipeline
---------------
1. Query expansion: Gemini generates 3 rephrasings of the question.
2. Embed all variants with gemini-embedding-001 (768-dim, retrieval_query).
3. Vector search in ChromaDB for each variant; union & deduplicate by chunk ID.
4. Confidence gate -- if top score < CONFIDENCE_THRESHOLD, return early.
5. Gemini reranking: score 0-10 relevance per chunk, keep top RAG_TOP_K >= 3.
6. Build numbered context block (parent chunk text, capped at 2000 chars).
7. Call Gemini 2.5 Flash with RAG_SYSTEM_PROMPT (max_tokens=1200).
"""

import json
import re as _re
import time
from datetime import datetime

from fastapi import HTTPException

from app.observability.logging import get_logger, log_llm_call
from app.rag.embedder import embed_query
from app.rag.vectorstore import get_chroma_client, get_or_create_collection, search

log = get_logger()

RAG_SYSTEM_PROMPT = """You are a document Q&A assistant. Answer STRICTLY from the numbered context excerpts provided below.

ABSOLUTE RULES:
1. ONLY use information explicitly stated in the excerpts. Never infer, extrapolate, or add outside knowledge.
2. Every factual claim MUST have a [n] citation marker from the specific excerpt -- no exceptions.
3. Answer the SPECIFIC question asked. Be precise -- include exact names, numbers, dates, dollar amounts, stages, and roles exactly as they appear in the excerpts. Do not paraphrase exact values.
4. Do not add surrounding context or background that the question did not ask for.
5. If the answer is NOT present in any excerpt, respond ONLY with: "The provided documents do not contain this information."
6. Answer in complete sentences. Be concise and direct -- only what the question asks for.
"""


def _expand_query(question: str, settings) -> list[str]:
    """Use Gemini to generate 3 rephrasings of the question to improve retrieval recall."""
    import json as _json

    from app.llm_provider import call_text_llm

    prompt = (
        "Generate 3 alternative phrasings of the following search query to improve document retrieval. "
        "Use synonyms, related business terms, and different angles that might appear in corporate documents.\n"
        "Return ONLY a JSON array of exactly 3 strings. No explanation, no markdown fences.\n\n"
        f"Query: {question}"
    )
    try:
        raw = call_text_llm(prompt, settings, response_json=False, max_tokens=250)
        m = _re.search(r"\[.*?\]", raw, _re.DOTALL)
        if m:
            variants = _json.loads(m.group(0))
            if isinstance(variants, list) and variants:
                return [question] + [v for v in variants if isinstance(v, str)][:3]
    except Exception:
        pass
    return [question]


def _extract_entities(question: str) -> list[str]:
    """Extract key entity terms from the question for keyword boosting."""
    import re as _re2

    # Grab capitalised multi-word phrases (company names, person names, product names)
    entities = _re2.findall(r"\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\b", question)
    # Also grab dollar amounts, years, stage words
    amounts = _re2.findall(r"\$[\d,]+|\b20\d\d\b", question)
    return list(dict.fromkeys(entities + amounts))  # deduplicate, preserve order


def _entity_boost(question: str, chunks: list[dict]) -> list[dict]:
    """Boost vector similarity score for chunks that contain key question entities."""
    entities = _extract_entities(question)
    if not entities:
        return chunks
    boosted = []
    for c in chunks:
        text_lower = c["text"].lower()
        hits = sum(1 for e in entities if e.lower() in text_lower)
        boost = 1.0 + (hits * 0.05)  # +5% per matching entity, capped naturally
        boosted.append({**c, "score": min(c["score"] * boost, 1.0)})
    return boosted


def _rrf_score(ranks: list[int], k: int = 60) -> float:
    """Reciprocal Rank Fusion score across multiple rank lists."""
    return sum(1.0 / (k + r) for r in ranks)


def _rerank_chunks(question: str, chunks: list[dict], settings, keep: int = 8) -> list[dict]:
    """
    Two-signal reranking:
    1. Gemini scores 0-10 per chunk with entity-aware, targeted prompt.
    2. RRF combines vector-similarity rank + Gemini reranker rank.
    Returns top `keep` by RRF score.
    """
    if not chunks or len(chunks) <= keep:
        return chunks
    import json as _json

    from app.llm_provider import call_text_llm

    entities = _extract_entities(question)
    entity_hint = f"Key entities to look for: {', '.join(entities)}.\n" if entities else ""

    excerpts = "\n\n".join(f"[{i + 1}] {c['text'][:600]}" for i, c in enumerate(chunks))
    prompt = (
        f"You are a relevance judge. Score each excerpt for how directly it answers the question.\n"
        f"{entity_hint}"
        f"Scoring guide:\n"
        f"  10 = contains the exact answer with specific facts (names, numbers, dates, dollar amounts)\n"
        f"   7 = mentions the topic with some relevant detail\n"
        f"   3 = tangentially related\n"
        f"   0 = unrelated\n"
        f"Return ONLY a JSON array of exactly {len(chunks)} integers. No explanation.\n\n"
        f"Question: {question}\n\nExcerpts:\n{excerpts}"
    )
    try:
        raw = call_text_llm(prompt, settings, response_json=False, max_tokens=200)
        m = _re.search(r"\[[\d\s,]+\]", raw)
        if m:
            scores = _json.loads(m.group(0))
            if isinstance(scores, list) and len(scores) == len(chunks):
                # Build reranker rank list (0-indexed, lower = better)
                reranker_ranks = [0] * len(chunks)
                for rank, (_, _score) in enumerate(
                    sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
                ):
                    reranker_ranks[_] = rank

                # Vector similarity rank (already sorted desc, so index = rank)
                vec_ranks = list(range(len(chunks)))

                # RRF fusion
                rrf_scores = [
                    _rrf_score([vec_ranks[i], reranker_ranks[i]]) for i in range(len(chunks))
                ]
                fused = sorted(zip(chunks, rrf_scores), key=lambda x: x[1], reverse=True)
                return [c for c, _ in fused[:keep]]
    except Exception:
        pass
    return chunks[:keep]


def _resolve_chunks_and_context(question: str, job_ids: list[str] | None, settings) -> dict:
    """Query expansion -> multi-variant search -> entity boost -> RRF rerank -> build prompt."""
    # Step 1: Query expansion
    query_variants = _expand_query(question, settings)

    client = get_chroma_client(settings)
    collection = get_or_create_collection(client, settings)

    # Step 2: Search with each variant, union & deduplicate by chunk ID
    seen_ids: set[str] = set()
    all_chunks: list[dict] = []
    initial_k = min(settings.RAG_TOP_K * 3, 30)  # wider initial net

    for variant in query_variants:
        q_embedding = embed_query(variant, settings)
        variant_chunks = search(collection, q_embedding, top_k=initial_k, job_ids=job_ids)
        for chunk in variant_chunks:
            if chunk["id"] not in seen_ids:
                seen_ids.add(chunk["id"])
                all_chunks.append(chunk)

    all_chunks.sort(key=lambda c: c["score"], reverse=True)

    if not all_chunks:
        if job_ids:
            msg = "The selected document(s) have no searchable text content. Try selecting different documents or search across all documents."
        else:
            msg = "No documents found to search. Please upload and process files first."
        return {
            "early_return": True,
            "payload": {
                "answer": msg,
                "citations": [],
                "confidence_gate_passed": False,
                "avg_similarity_score": 0.0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "latency_ms": 0,
                "ragas_scores": None,
            },
        }

    top_score = all_chunks[0]["score"]

    if top_score < settings.CONFIDENCE_THRESHOLD:
        return {
            "early_return": True,
            "payload": {
                "answer": "I couldn't find sufficiently relevant information in your documents to answer this question confidently.",
                "citations": [],
                "confidence_gate_passed": False,
                "avg_similarity_score": top_score,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "latency_ms": 0,
                "ragas_scores": None,
            },
        }

    # Step 3: Entity boost then RRF rerank — keep best RAG_TOP_K chunks
    boosted = _entity_boost(question, all_chunks[:30])
    boosted.sort(key=lambda c: c["score"], reverse=True)
    reranked = _rerank_chunks(question, boosted[:25], settings, keep=settings.RAG_TOP_K)
    avg_score = sum(c["score"] for c in reranked) / len(reranked)

    _MAX_CHUNK_CHARS = 2000
    context_parts = [
        f"[{i}] Source: {c['filename']} ({c['page_or_segment']})\n{c['text'][:_MAX_CHUNK_CHARS]}"
        for i, c in enumerate(reranked, 1)
    ]
    user_prompt = f"Context:\n{chr(10).join(context_parts)}\n\nQuestion: {question}\n\nAnswer (with [n] citation markers):"
    return {
        "early_return": False,
        "chunks": reranked,
        "avg_score": avg_score,
        "user_prompt": user_prompt,
    }


def query(
    question: str,
    job_ids: list[str] | None,
    user_id,
    db,
    settings,
) -> dict:
    start_total = time.time()

    resolved = _resolve_chunks_and_context(question, job_ids, settings)
    if resolved["early_return"]:
        payload = resolved["payload"]
        payload["latency_ms"] = int((time.time() - start_total) * 1000)
        log.info(
            "rag_query_early_exit", question=question[:100], reason="no_chunks_or_low_confidence"
        )
        return payload

    chunks = resolved["chunks"]
    avg_score = resolved["avg_score"]
    user_prompt = resolved["user_prompt"]

    from app.llm_provider import call_query_llm

    try:
        answer_text, prompt_tokens, completion_tokens = call_query_llm(
            messages=[
                {"role": "system", "content": RAG_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            settings=settings,
            temperature=0,
        )
    except Exception as exc:
        msg = str(exc).lower()
        if "429" in msg or "rate" in msg or "quota" in msg:
            log.warning("rag_rate_limit", model=settings.GEMINI_MODEL, error=str(exc)[:200])
            raise HTTPException(
                status_code=429,
                detail="AI model rate limit reached. Please wait a few minutes and try again.",
            )
        if "413" in msg or "too large" in msg:
            log.warning("rag_request_too_large", model=settings.GEMINI_MODEL, error=str(exc)[:200])
            raise HTTPException(
                status_code=503,
                detail="Query context too large for model. Try selecting fewer documents.",
            )
        log.error("rag_api_error", model=settings.GEMINI_MODEL, error=str(exc)[:200])
        raise HTTPException(status_code=502, detail="AI model error. Please try again.")

    latency_ms = int((time.time() - start_total) * 1000)

    log_llm_call(
        user_id=user_id,
        endpoint="rag_query",
        model=settings.GEMINI_MODEL,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        query_text=question[:500],
        llm_response_preview=answer_text[:500],
        db=db,
    )

    log.info(
        "rag_query",
        question=question[:100],
        retrieved_chunk_count=len(chunks),
        avg_similarity_score=round(avg_score, 4),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
    )

    citations = [
        {
            "index": i + 1,
            "filename": c["filename"],
            "page_or_segment": c["page_or_segment"],
            "excerpt": c["text"][:200],
        }
        for i, c in enumerate(chunks)
    ]

    from app.models.db import QueryHistory

    qh = QueryHistory(
        user_id=user_id,
        question=question,
        answer=answer_text,
        citations=json.dumps(citations),
        job_ids_queried=json.dumps([str(j) for j in (job_ids or [])]),
        chunk_count_retrieved=len(chunks),
        avg_similarity_score=avg_score,
        confidence_gate_passed=True,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        created_at=datetime.utcnow(),
    )
    db.add(qh)
    db.commit()
    db.refresh(qh)

    from app.workers.tasks import compute_ragas

    compute_ragas.apply_async(args=[str(qh.id)], task_id=f"ragas-{qh.id}")

    return {
        "answer": answer_text,
        "citations": citations,
        "confidence_gate_passed": True,
        "avg_similarity_score": avg_score,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "latency_ms": latency_ms,
        "ragas_scores": None,
    }
