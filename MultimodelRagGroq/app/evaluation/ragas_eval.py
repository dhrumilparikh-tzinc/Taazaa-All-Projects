"""
RAGAS quality evaluation for RAG query responses.

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
- Uses Groq (GROQ_PROCESSING_MODEL = llama-3.1-8b-instant) via LangChain as
  the evaluator LLM.  The 500k TPD quota on llama-3.1-8b-instant means RAGAS
  rarely hits rate limits even at moderate query volumes.
- RAGAS default strictness=3 batches 3 LLM calls per metric in one request;
  Groq only supports n=1 so strictness is set to 1.
- Each context is truncated to 800 chars before sending to RAGAS to stay
  within the 6k TPM per-request limit.
- Auto-retries once after 65 s on 429 rate-limit errors.
"""

import os
import warnings

os.environ["RAGAS_DO_NOT_TRACK"] = "true"
# Suppress Python 3.14 asyncio "Event loop is closed" noise from httpx cleanup
warnings.filterwarnings("ignore")
os.environ.setdefault("PYTHONWARNINGS", "ignore")

from app.observability.logging import get_logger

log = get_logger()


def get_ragas_llm(settings):
    from app.llm_provider import get_ragas_llm_wrapper

    return get_ragas_llm_wrapper(settings)


class _FastEmbedLangChainEmbeddings:
    """Reuse the fastembed singleton already loaded by app.rag.embedder.
    Avoids loading a second PyTorch model (HuggingFaceEmbeddings) alongside
    fastembed (ONNX Runtime), which crashes on Python 3.14 when the cross-encoder
    reranker (also PyTorch) is present in the same process."""

    def __init__(self, model_name: str):
        self._model_name = model_name

    def _m(self):
        from app.rag.embedder import _get_model

        return _get_model(self._model_name)

    def embed_documents(self, texts: list) -> list:
        return [v.tolist() for v in self._m().embed(texts)]

    def embed_query(self, text: str) -> list:
        return next(self._m().query_embed(text)).tolist()

    async def aembed_documents(self, texts: list) -> list:
        return self.embed_documents(texts)

    async def aembed_query(self, text: str) -> list:
        return self.embed_query(text)


def get_ragas_embeddings(settings):
    from app.llm_provider import get_ragas_embeddings_wrapper

    return get_ragas_embeddings_wrapper(settings)


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

        # Truncate each context to 1500 chars — parent chunks are ~600 words
        # (~3600 chars), so 800 chars was cutting off most of the content and
        # causing artificially low context_recall. 1500 chars ≈ 250 words, which
        # retains the key facts while staying within the 8b model's token budget.
        truncated_contexts = [c[:1500] for c in (contexts or [])]

        sample = SingleTurnSample(
            user_input=question,
            response=answer,
            retrieved_contexts=truncated_contexts,
            reference=ground_truth,
        )
        dataset = EvaluationDataset(samples=[sample])

        llm = get_ragas_llm(settings)
        embeddings = get_ragas_embeddings(settings)

        # Faithfulness + AnswerRelevancy work without ground truth.
        # ContextPrecision, ContextRecall, AnswerCorrectness all require a
        # reference answer — only include them when ground_truth is provided.
        # strictness=1 → single question generation per sample.
        # Groq only supports n=1 per request; RAGAS default strictness=3
        # batches n=3 in one call which Groq rejects with 400.
        metrics = [Faithfulness(), AnswerRelevancy(strictness=1)]
        if ground_truth:
            metrics += [ContextPrecision(), ContextRecall(), AnswerCorrectness()]

        result = evaluate(
            dataset=dataset,
            metrics=metrics,
            llm=llm,
            embeddings=embeddings,
        )
        scores = result.to_pandas().iloc[0].to_dict()
        metric_keys = ["faithfulness", "answer_relevancy"]
        if ground_truth:
            metric_keys += ["context_precision", "context_recall", "answer_correctness"]
        return {k: float(scores[k]) for k in metric_keys if k in scores and str(scores[k]) != "nan"}

    except Exception as e:
        err_str = str(e)
        # Retry on rate limit (429) OR timeout — both indicate the evaluator LLM
        # was overwhelmed. llama-3.1-8b has 6k TPM; RAGAS fires ~25 concurrent
        # calls which can saturate the budget. 90s cooldown allows replenishment.
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
