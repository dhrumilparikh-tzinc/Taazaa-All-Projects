"""
Offline RAGAS baseline evaluation -- Gemini-only.

Usage:
    py scripts/ragas_baseline.py [--test-set /path/to/test_set.json]

Runs each question through:
  1. Gemini query expansion (3 rephrasings)
  2. Multi-variant ChromaDB retrieval + deduplication
  3. Gemini reranking (0-10 per chunk, keep top RAG_TOP_K scoring >= 3)
  4. Gemini 2.5 Flash answer generation
  5. RAGAS faithfulness + answer_relevancy + precision/recall/correctness

Saves results to C:/tmp/ragas_baseline.json and prints a summary table.
"""

import json
import sys
import time
import argparse
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
DATABASE_URL = os.environ["DATABASE_URL"]

from sqlmodel import Session, create_engine, select
engine = create_engine(DATABASE_URL, echo=False)


def _expand_query(question: str, settings) -> list:
    """Gemini query expansion -- 3 rephrasings for better recall."""
    import json as _json, re as _re
    from app.llm_provider import call_text_llm
    prompt = (
        "Generate 3 alternative phrasings of the following search query to improve document retrieval. "
        "Use synonyms, related business terms, and different angles that might appear in corporate documents.\n"
        "Return ONLY a JSON array of exactly 3 strings. No explanation, no markdown fences.\n\n"
        f"Query: {question}"
    )
    try:
        raw = call_text_llm(prompt, settings, response_json=False, max_tokens=250)
        m = _re.search(r'\[.*?\]', raw, _re.DOTALL)
        if m:
            variants = _json.loads(m.group(0))
            if isinstance(variants, list) and variants:
                return [question] + [v for v in variants if isinstance(v, str)][:3]
    except Exception:
        pass
    return [question]


def _extract_entities(question: str) -> list:
    """Extract key entity terms from the question for keyword boosting."""
    import re as _re2
    entities = _re2.findall(r'\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\b', question)
    amounts  = _re2.findall(r'\$[\d,]+|\b20\d\d\b', question)
    return list(dict.fromkeys(entities + amounts))


def _entity_boost(question: str, chunks: list) -> list:
    """Boost vector similarity score for chunks containing key question entities."""
    entities = _extract_entities(question)
    if not entities:
        return chunks
    boosted = []
    for c in chunks:
        text_lower = c["text"].lower()
        hits = sum(1 for e in entities if e.lower() in text_lower)
        boost = 1.0 + (hits * 0.05)
        boosted.append({**c, "score": min(c["score"] * boost, 1.0)})
    return boosted


def _rrf_score(ranks: list, k: int = 60) -> float:
    """Reciprocal Rank Fusion score across multiple rank lists."""
    return sum(1.0 / (k + r) for r in ranks)


def _rerank_chunks(question: str, chunks: list, settings, keep: int = 8) -> list:
    """Entity-aware Gemini reranking with RRF fusion of vector + reranker ranks."""
    if not chunks or len(chunks) <= keep:
        return chunks
    import json as _json, re as _re
    from app.llm_provider import call_text_llm

    entities = _extract_entities(question)
    entity_hint = f"Key entities to look for: {', '.join(entities)}.\n" if entities else ""

    excerpts = "\n\n".join(f"[{i+1}] {c['text'][:600]}" for i, c in enumerate(chunks))
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
        m = _re.search(r'\[[\d\s,]+\]', raw)
        if m:
            scores = _json.loads(m.group(0))
            if isinstance(scores, list) and len(scores) == len(chunks):
                reranker_ranks = [0] * len(chunks)
                for rank, (idx, _score) in enumerate(
                    sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
                ):
                    reranker_ranks[idx] = rank

                vec_ranks = list(range(len(chunks)))
                rrf_scores = [
                    _rrf_score([vec_ranks[i], reranker_ranks[i]])
                    for i in range(len(chunks))
                ]
                fused = sorted(zip(chunks, rrf_scores), key=lambda x: x[1], reverse=True)
                return [c for c, _ in fused[:keep]]
    except Exception:
        pass
    return chunks[:keep]


RAG_SYSTEM_PROMPT = (
    "You are a document Q&A assistant. Answer STRICTLY from the numbered context excerpts provided below.\n\n"
    "ABSOLUTE RULES:\n"
    "1. ONLY use information explicitly stated in the excerpts. Never infer, extrapolate, or add outside knowledge.\n"
    "2. Every factual claim MUST have a [n] citation marker from the specific excerpt -- no exceptions.\n"
    "3. Answer the SPECIFIC question asked. Be precise -- include exact names, numbers, dates, dollar amounts, "
    "stages, and roles exactly as they appear in the excerpts. Do not paraphrase exact values.\n"
    "4. Do not add surrounding context or background that the question did not ask for.\n"
    "5. If the answer is NOT present in any excerpt, respond ONLY with: "
    "'The provided documents do not contain this information.'\n"
    "6. Answer in complete sentences. Be concise and direct -- only what the question asks for.\n"
)


def _rag_query(question: str, job_ids, settings) -> tuple:
    """Query expansion -> entity boost -> RRF rerank -> Gemini answer. Returns (answer, contexts)."""
    from app.rag.embedder import embed_query
    from app.rag.vectorstore import get_chroma_client, get_or_create_collection, search

    query_variants = _expand_query(question, settings)
    client = get_chroma_client(settings)
    col = get_or_create_collection(client, settings)

    seen_ids = set()
    all_chunks = []
    initial_k = min(settings.RAG_TOP_K * 3, 30)  # wider initial net

    for variant in query_variants:
        q_emb = embed_query(variant, settings)
        for chunk in search(col, q_emb, top_k=initial_k, job_ids=job_ids or None):
            if chunk["id"] not in seen_ids:
                seen_ids.add(chunk["id"])
                all_chunks.append(chunk)

    all_chunks.sort(key=lambda c: c["score"], reverse=True)

    if not all_chunks:
        return "No relevant documents found.", []

    top_score = all_chunks[0]["score"]
    if top_score < settings.CONFIDENCE_THRESHOLD:
        return "The provided documents do not contain this information.", []

    boosted = _entity_boost(question, all_chunks[:30])
    boosted.sort(key=lambda c: c["score"], reverse=True)
    chunks = _rerank_chunks(question, boosted[:25], settings, keep=settings.RAG_TOP_K)
    contexts = [c["text"] for c in chunks]

    ctx_block = "\n\n".join(
        f"[{i+1}] {c['filename']} ({c['page_or_segment']}):\n{c['text'][:2000]}"
        for i, c in enumerate(chunks)
    )
    prompt = (
        f"{RAG_SYSTEM_PROMPT}\n"
        f"Context:\n{ctx_block}\n\n"
        f"Question: {question}\n\nAnswer (with [n] citation markers):"
    )

    from app.llm_provider import call_text_llm
    for attempt in range(4):
        try:
            answer = call_text_llm(prompt, settings, response_json=False, max_tokens=1200)
            return answer, contexts
        except Exception as e:
            if ("429" in str(e) or "quota" in str(e).lower()) and attempt < 3:
                wait = 60 * (attempt + 1)
                print(f"  [rate limit] waiting {wait}s...")
                time.sleep(wait)
                continue
            raise

    return "Rate limit -- could not generate answer.", contexts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-set", default="C:/tmp/ragas_test_set.json")
    args = parser.parse_args()

    test_set_path = Path(args.test_set)
    if not test_set_path.exists():
        print(f"[ERROR] Test set not found: {test_set_path}")
        sys.exit(1)

    with open(test_set_path) as f:
        test_set = json.load(f)

    print(f"Loaded {len(test_set)} Q&A pairs from {test_set_path}")

    from app.config import settings
    from app.evaluation.ragas_eval import compute_ragas_scores

    print(f"LLM: Gemini 2.5 Flash  |  Embeddings: {settings.GEMINI_EMBEDDING_MODEL}")
    print(f"Pipeline: query expansion + entity boost + RRF reranking (Gemini-scored)")

    results = []
    col_w = 45

    print(f"\n{'Question':<{col_w}} {'Faith':>6} {'AnswRel':>7} {'CtxPrec':>8} {'CtxRec':>7} {'AnsCorr':>8}")
    print("-" * (col_w + 42))

    with Session(engine) as db:
        for idx, item in enumerate(test_set):
            question     = item["question"]
            ground_truth = item.get("ground_truth")
            job_id       = item.get("job_id")
            job_ids      = [job_id] if job_id else None

            try:
                answer, full_contexts = _rag_query(question, job_ids, settings)
                ragas_contexts = [c[:1500] for c in (full_contexts or ["(no context retrieved)"])]

                scores = compute_ragas_scores(
                    question=question,
                    answer=answer,
                    contexts=ragas_contexts,
                    ground_truth=ground_truth,
                    settings=settings,
                )

                faith = scores.get("faithfulness", float("nan"))
                rel   = scores.get("answer_relevancy", float("nan"))
                prec  = scores.get("context_precision", float("nan"))
                rec   = scores.get("context_recall", float("nan"))
                corr  = scores.get("answer_correctness", float("nan"))

                q_short = question[:col_w - 3] + "..." if len(question) > col_w else question
                print(f"{q_short:<{col_w}} {faith:>6.3f} {rel:>7.3f} {prec:>8.3f} {rec:>7.3f} {corr:>8.3f}")

                results.append({
                    "question": question,
                    "ground_truth": ground_truth,
                    "answer": answer,
                    "scores": scores,
                })

            except Exception as e:
                q_short = question[:50]
                print(f"[SKIP] {q_short}: {e}")
                results.append({"question": question, "error": str(e)})

            if idx < len(test_set) - 1:
                time.sleep(5)

    metric_keys = ["faithfulness", "answer_relevancy", "context_precision", "context_recall", "answer_correctness"]
    sums   = {k: 0.0 for k in metric_keys}
    counts = {k: 0   for k in metric_keys}
    for r in results:
        for k in metric_keys:
            v = r.get("scores", {}).get(k)
            if isinstance(v, float) and not __import__("math").isnan(v):
                sums[k]   += v
                counts[k] += 1
    avgs = {k: round(sums[k] / counts[k], 4) if counts[k] else None for k in metric_keys}

    print("\n" + "=" * 60)
    print("BASELINE AVERAGES")
    print("=" * 60)
    targets = {k: 0.80 for k in metric_keys}
    for k, v in avgs.items():
        target = targets[k]
        status = "PASS" if v and v >= target else "BELOW TARGET"
        print(f"  {k:<25} {str(v) if v is not None else 'N/A':>8}  (target >= {target}) {status}")

    out_path = Path("C:/tmp/ragas_baseline.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"results": results, "averages": avgs}, f, indent=2)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
