"""
Offline RAGAS baseline evaluation.
Usage: py scripts/ragas_baseline.py [--test-set /path/to/test_set.json]
"""

import argparse
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent))

import os

import pandas  # noqa: F401

# pyarrow and ONNX Runtime (fastembed) both register native DLL hooks on Windows.
# Loading pyarrow AFTER ONNX Runtime causes an access violation on Python 3.14.
# Pre-importing pyarrow here (before any app.rag imports touch fastembed) fixes the crash.
import pyarrow  # noqa: F401
from sqlmodel import Session, create_engine, select

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL, echo=False)


def _rag_query_with_retry(question, job_ids, user_id, db, settings, max_wait=600):
    """Full pipeline (embed → hybrid search → rerank) + Groq answer generation.
    RAGAS embeddings now reuse the fastembed singleton via _FastEmbedLangChainEmbeddings,
    so no second PyTorch model is loaded — fastembed (ONNX) + CrossEncoder (PyTorch)
    coexist safely, as proven by check_scores.py."""
    import groq as groq_sdk

    from app.rag.engine import _resolve_chunks_and_context

    resolved = _resolve_chunks_and_context(question, job_ids, settings)
    if resolved["early_return"]:
        return resolved["payload"]["answer"], []

    chunks = resolved["chunks"]
    user_prompt = resolved["user_prompt"]
    full_contexts = [c["text"] for c in chunks]

    groq_client = groq_sdk.Groq(api_key=settings.GROQ_API_KEY)
    for attempt in range(5):
        try:
            resp = groq_client.chat.completions.create(
                model=settings.GROQ_MODEL,
                temperature=0,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a document Q&A assistant. Answer STRICTLY from the numbered context excerpts provided below.\n\n"
                            "ABSOLUTE RULES — violating any of these is wrong:\n"
                            "1. ONLY use information explicitly stated word-for-word in the excerpts. Never add, infer, or extrapolate.\n"
                            "2. Every factual claim MUST have a [n] citation marker pointing to the specific excerpt it came from.\n"
                            "3. Include ALL relevant details from the context that answer the question — names, numbers, dates, categories, stages. Do not omit any relevant fact.\n"
                            "4. If the exact answer is NOT present in any excerpt, respond ONLY with: "
                            "'The provided documents do not contain this information.' — nothing else.\n"
                            "5. Do NOT paraphrase or summarise context in a way that adds meaning not written there.\n"
                            "6. Do NOT use your training knowledge. Treat the excerpts as the only source of truth.\n"
                            "7. Answer in complete sentences, not bare lists. Direct and factual."
                        ),
                    },
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=800,
            )
            answer = resp.choices[0].message.content
            return answer, full_contexts
        except groq_sdk.RateLimitError as e:
            wait = 60 * (attempt + 1)
            print(f"  [RAG 429] waiting {wait}s... ({e!s:.80})")
            time.sleep(wait)
    return "Rate limit — could not generate answer.", full_contexts


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

    results = []
    col_w = 45

    print(
        f"\n{'Question':<{col_w}} {'Faith':>6} {'AnswRel':>7} {'CtxPrec':>8} {'CtxRec':>7} {'AnsCorr':>8}"
    )
    print("-" * (col_w + 42))

    with Session(engine) as db:
        for item in test_set:
            question = item["question"]
            ground_truth = item.get("ground_truth")
            job_id = item.get("job_id")
            job_ids = [job_id] if job_id else None

            from app.models.db import Job, User

            user_id = None
            if job_id:
                job = db.get(Job, __import__("uuid").UUID(job_id))
                if job:
                    user_id = job.user_id
            if not user_id:
                user = db.exec(select(User)).first()
                user_id = user.id if user else None

            try:
                answer, full_contexts = _rag_query_with_retry(
                    question, job_ids, user_id, db, settings
                )
                if not full_contexts:
                    full_contexts = ["(no context retrieved)"]

                # 1500 chars per chunk (≈250 words) — parent chunks are ~600 words
                # (~3600 chars). The old 600-char cutoff was losing most of the content,
                # causing artificially low context_recall. 1500 chars gives RAGAS
                # enough text to find the ground-truth facts.
                ragas_contexts = [c[:1500] for c in full_contexts]

                scores = compute_ragas_scores(
                    question=question,
                    answer=answer,
                    contexts=ragas_contexts,
                    ground_truth=ground_truth,
                    settings=settings,
                )

                faith = scores.get("faithfulness", float("nan"))
                rel = scores.get("answer_relevancy", float("nan"))
                prec = scores.get("context_precision", float("nan"))
                rec = scores.get("context_recall", float("nan"))
                corr = scores.get("answer_correctness", float("nan"))

                q_short = question[: col_w - 3] + "..." if len(question) > col_w else question
                print(
                    f"{q_short:<{col_w}} {faith:>6.3f} {rel:>7.3f} {prec:>8.3f} {rec:>7.3f} {corr:>8.3f}"
                )

                results.append(
                    {
                        "question": question,
                        "ground_truth": ground_truth,
                        "answer": answer,
                        "scores": scores,
                    }
                )

            except Exception as e:
                print(f"[SKIP] {question[:50]}: {e}")
                results.append({"question": question, "error": str(e)})

            # 60s between questions — llama-3.1-8b has 6k TPM; RAGAS makes
            # ~5 LLM calls per metric × 5 metrics ≈ 25 calls × ~500 tok = 12.5k tok.
            # At 6k TPM, need ≥2 min budget. 60s + evaluation time ≈ safe.
            time.sleep(60)

    metric_keys = [
        "faithfulness",
        "answer_relevancy",
        "context_precision",
        "context_recall",
        "answer_correctness",
    ]
    sums = {k: 0.0 for k in metric_keys}
    counts = {k: 0 for k in metric_keys}
    for r in results:
        for k in metric_keys:
            v = r.get("scores", {}).get(k)
            if isinstance(v, float) and not __import__("math").isnan(v):
                sums[k] += v
                counts[k] += 1
    avgs = {k: round(sums[k] / counts[k], 4) if counts[k] else None for k in metric_keys}

    print("\n" + "=" * 60)
    print("BASELINE AVERAGES")
    print("=" * 60)
    for k, v in avgs.items():
        target = {"faithfulness": 0.8}.get(k, 0.7)
        status = "PASS" if v and v >= target else "BELOW TARGET"
        print(f"  {k:<25} {str(v) if v is not None else 'N/A':>8}  (target >= {target}) {status}")

    out_path = Path("C:/tmp/ragas_baseline.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"results": results, "averages": avgs}, f, indent=2)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
