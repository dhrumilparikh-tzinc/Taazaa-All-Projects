"""
RAGAS quality evaluation for RAG query responses — Gemini-only.

compute_ragas_scores() is called asynchronously by the compute_ragas Celery
task after every successful RAG query.  It never blocks the query response.

Metrics computed
----------------
Always (no ground truth needed):
  faithfulness       — every claim in the answer is grounded in the context.
  answer_relevancy   — the answer addresses the question asked.

With ground_truth only:
  context_precision  — proportion of retrieved chunks that were relevant.
  context_recall     — proportion of ground truth covered by the context.
  answer_correctness — answer matches the reference answer.

Implementation notes
--------------------
- Uses Gemini 2.5 Flash via LangChain as the evaluator LLM.
- Embeddings use Gemini text-embedding-004 (768-dim).
- Each context is truncated to 1500 chars to stay within token budgets.
- Auto-retries once after 90 s on rate-limit errors.
"""

import os
import warnings

os.environ["RAGAS_DO_NOT_TRACK"] = "true"
warnings.filterwarnings("ignore")
os.environ.setdefault("PYTHONWARNINGS", "ignore")

from app.observability.logging import get_logger

log = get_logger()


def get_ragas_llm(settings):
    from app.llm_provider import get_ragas_llm_wrapper

    return get_ragas_llm_wrapper(settings)


def get_ragas_embeddings(settings):
    from app.llm_provider import get_ragas_embeddings_wrapper

    return get_ragas_embeddings_wrapper(settings)


def _synthesize_ground_truth(question: str, contexts: list[str], settings) -> str | None:
    """Ask the LLM to produce a reference answer from the context for reference-based metrics."""
    from app.llm_provider import call_text_llm

    ctx_block = "\n\n".join(contexts[:6])
    prompt = (
        "You are a reference-answer generator for RAG evaluation.\n"
        "Using ONLY the excerpts below, write a concise, factually complete answer "
        "to the question. Do not add information not present in the excerpts.\n\n"
        f"Question: {question}\n\nExcerpts:\n{ctx_block}\n\nReference answer:"
    )
    try:
        return call_text_llm(prompt, settings, response_json=False, max_tokens=400)
    except Exception:
        return None


def compute_ragas_scores(
    question: str,
    answer: str,
    contexts: list[str],
    ground_truth: str | None,
    settings,
) -> dict:
    try:
        from ragas import EvaluationDataset, SingleTurnSample, evaluate
        from ragas.metrics import (
            AnswerCorrectness,
            AnswerRelevancy,
            ContextPrecision,
            ContextRecall,
            Faithfulness,
        )

        truncated_contexts = [c[:1500] for c in (contexts or [])]

        # Synthesize a reference answer when ground truth is not provided so
        # that all 5 metrics can be computed for every live query.
        effective_ground_truth = ground_truth
        if not effective_ground_truth and truncated_contexts:
            effective_ground_truth = _synthesize_ground_truth(
                question, truncated_contexts, settings
            )

        sample = SingleTurnSample(
            user_input=question,
            response=answer,
            retrieved_contexts=truncated_contexts,
            reference=effective_ground_truth,
        )
        dataset = EvaluationDataset(samples=[sample])

        llm = get_ragas_llm(settings)
        embeddings = get_ragas_embeddings(settings)

        metrics = [Faithfulness(), AnswerRelevancy(strictness=1)]
        if effective_ground_truth:
            metrics += [ContextPrecision(), ContextRecall(), AnswerCorrectness()]

        result = evaluate(
            dataset=dataset,
            metrics=metrics,
            llm=llm,
            embeddings=embeddings,
        )
        scores = result.to_pandas().iloc[0].to_dict()
        metric_keys = ["faithfulness", "answer_relevancy"]
        if effective_ground_truth:
            metric_keys += ["context_precision", "context_recall", "answer_correctness"]
        return {k: float(scores[k]) for k in metric_keys if k in scores and str(scores[k]) != "nan"}

    except Exception as e:
        err_str = str(e)
        is_retriable = (
            "429" in err_str
            or "rate_limit" in err_str.lower()
            or "RateLimitError" in err_str
            or "TimeoutError" in err_str
            or "timed out" in err_str.lower()
            or "timeout" in err_str.lower()
        )
        if is_retriable:
            log.warning("ragas_rate_limit_retry", wait_s=90, error=err_str[:120])
            import time as _time

            _time.sleep(90)
            try:
                result = evaluate(dataset=dataset, metrics=metrics, llm=llm, embeddings=embeddings)
                scores = result.to_pandas().iloc[0].to_dict()
                return {
                    k: float(scores[k])
                    for k in metric_keys
                    if k in scores and str(scores[k]) != "nan"
                }
            except Exception as e2:
                log.error("ragas_eval_error_after_retry", error=str(e2))
                return {"error": str(e2)}
        log.error("ragas_eval_error", error=err_str)
        return {"error": err_str}
