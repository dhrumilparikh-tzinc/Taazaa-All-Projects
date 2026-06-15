"""
Gemini-only LLM and embedding factory.

All LLM, vision, embedding, and RAGAS evaluation calls route exclusively
through Google Gemini APIs (google-genai SDK).

Functions
---------
call_text_llm()                 text completion (JSON or plain) via Gemini
call_vision_llm()               vision completion via Gemini
call_query_llm()                RAG answer generation via Gemini
embed_query_text()              single-vector embed (retrieval_query)
embed_batch_texts()             batch embed for document chunking (retrieval_document)
get_ragas_llm_wrapper()         RAGAS-compatible LangChain LLM wrapper (Gemini)
get_ragas_embeddings_wrapper()  RAGAS-compatible LangChain embeddings wrapper (Gemini)
"""

from __future__ import annotations

import json
import re
import threading
import time

# ── Global rate limiter — Gemini free tier: 15 RPM for generation, 100 RPM for embedding ──
_gen_lock = threading.Lock()
_embed_lock = threading.Lock()
_last_gen_call = 0.0
_last_embed_call = 0.0

# ── Session-level token accumulator ──────────────────────────────────────────
_token_lock = threading.Lock()
_session_prompt_tokens = 0
_session_completion_tokens = 0
_session_embed_tokens = 0


def _accum_gen(prompt_tokens: int, completion_tokens: int) -> None:
    global _session_prompt_tokens, _session_completion_tokens
    with _token_lock:
        _session_prompt_tokens += prompt_tokens
        _session_completion_tokens += completion_tokens


def _accum_embed(tokens: int) -> None:
    global _session_embed_tokens
    with _token_lock:
        _session_embed_tokens += tokens


def get_session_token_counts() -> dict:
    """Return cumulative token counts since process start."""
    with _token_lock:
        pt = _session_prompt_tokens
        ct = _session_completion_tokens
        et = _session_embed_tokens
    # Gemini 2.5 Flash pricing (per 1M tokens, ≤200K context)
    gen_input_cost = (pt / 1_000_000) * 0.15
    gen_output_cost = (ct / 1_000_000) * 0.60
    # Gemini Embedding 2 pricing
    embed_cost = (et / 1_000_000) * 0.04
    return {
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "embed_tokens": et,
        "estimated_usd": round(gen_input_cost + gen_output_cost + embed_cost, 4),
        "gen_input_cost_usd": round(gen_input_cost, 4),
        "gen_output_cost_usd": round(gen_output_cost, 4),
        "embed_cost_usd": round(embed_cost, 6),
    }


_GEN_MIN_INTERVAL = 2.0  # seconds → max ~30 RPM (well within 1000 RPM paid tier)
_EMBED_MIN_INTERVAL = 0.3  # seconds → max ~200 RPM


def _throttle_gen():
    """Block until at least _GEN_MIN_INTERVAL seconds since last generation call."""
    global _last_gen_call
    with _gen_lock:
        elapsed = time.time() - _last_gen_call
        wait = _GEN_MIN_INTERVAL - elapsed
        _last_gen_call = time.time() + max(0.0, wait)
    if wait > 0:
        time.sleep(wait)  # sleep outside the lock so it doesn't block other threads


def _throttle_embed():
    """Block until at least _EMBED_MIN_INTERVAL seconds since last embed call."""
    global _last_embed_call
    with _embed_lock:
        elapsed = time.time() - _last_embed_call
        wait = _EMBED_MIN_INTERVAL - elapsed
        _last_embed_call = time.time() + max(0.0, wait)
    if wait > 0:
        time.sleep(wait)


def _safe_parse_json(text: str) -> dict:
    """Parse JSON from Gemini response, handling markdown fences and truncated output."""
    if not text:
        return {}

    # Strip markdown code fences: ```json ... ``` or ``` ... ```
    stripped = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    stripped = re.sub(r"\s*```$", "", stripped.strip())
    stripped = stripped.strip()

    # Try direct parse first
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # Try to extract the first { ... } block
    match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Last resort: truncated JSON — try appending closing chars
    for suffix in ['"}', '"]}', "]}", "}"]:
        try:
            return json.loads(stripped + suffix)
        except json.JSONDecodeError:
            continue

    return {}


# ── Text LLM ──────────────────────────────────────────────────────────────────


def call_text_llm(
    prompt: str,
    settings,
    response_json: bool = False,
    max_tokens: int | None = 1024,
    system_prompt: str | None = None,
) -> str | dict:
    """Call Gemini text LLM and return a string (or parsed dict when response_json=True)."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    config = types.GenerateContentConfig(
        **({} if max_tokens is None else {"max_output_tokens": max_tokens})
    )
    if response_json:
        config.response_mime_type = "application/json"
    if system_prompt:
        config.system_instruction = system_prompt

    for attempt in range(5):
        try:
            _throttle_gen()
            resp = client.models.generate_content(
                model=settings.GEMINI_MODEL, contents=prompt, config=config
            )
            text = resp.text or ""
            if resp.usage_metadata:
                _accum_gen(
                    resp.usage_metadata.prompt_token_count or 0,
                    resp.usage_metadata.candidates_token_count or 0,
                )
            if response_json:
                return _safe_parse_json(text)
            return text
        except Exception as e:
            msg = str(e)
            if (
                "429" in msg or "quota" in msg.lower() or "RESOURCE_EXHAUSTED" in msg
            ) and attempt < 4:
                wait = 60 * (2**attempt)  # 60, 120, 240, 480 seconds
                time.sleep(wait)
                continue
            raise
    raise RuntimeError("call_text_llm: exhausted retries")


# ── Vision LLM ────────────────────────────────────────────────────────────────


def call_vision_llm(
    prompt: str,
    image_data: bytes,
    mime_type: str,
    settings,
    response_json: bool = False,
    max_tokens: int = 2048,
) -> str | dict:
    """Call Gemini vision LLM and return a string (or parsed dict when response_json=True)."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    config = types.GenerateContentConfig(max_output_tokens=max_tokens)
    if response_json:
        config.response_mime_type = "application/json"

    image_part = types.Part.from_bytes(data=image_data, mime_type=mime_type)
    for attempt in range(5):
        try:
            _throttle_gen()
            resp = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=[image_part, prompt],
                config=config,
            )
            text = resp.text or ""
            if resp.usage_metadata:
                _accum_gen(
                    resp.usage_metadata.prompt_token_count or 0,
                    resp.usage_metadata.candidates_token_count or 0,
                )
            if response_json:
                return _safe_parse_json(text)
            return text
        except Exception as e:
            msg = str(e)
            if (
                "429" in msg or "quota" in msg.lower() or "RESOURCE_EXHAUSTED" in msg
            ) and attempt < 4:
                wait = 60 * (2**attempt)
                time.sleep(wait)
                continue
            raise
    raise RuntimeError("call_vision_llm: exhausted retries")


# ── Query LLM (RAG answer generation) ─────────────────────────────────────────


def call_query_llm(
    messages: list[dict],
    settings,
    max_tokens: int | None = None,
    temperature: float = 0,
) -> tuple[str, int, int]:
    """
    Call Gemini for RAG answer generation.
    Returns (answer_text, prompt_tokens, completion_tokens).
    No token cap — model writes as much as the answer needs.
    """
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    system_text = None
    contents = []
    for m in messages:
        if m["role"] == "system":
            system_text = m["content"]
        else:
            role = "user" if m["role"] == "user" else "model"
            contents.append(
                types.Content(role=role, parts=[types.Part.from_text(text=m["content"])])
            )

    config = types.GenerateContentConfig(
        **({} if max_tokens is None else {"max_output_tokens": max_tokens})
    )
    if system_text:
        config.system_instruction = system_text

    _throttle_gen()
    resp = client.models.generate_content(
        model=settings.GEMINI_MODEL, contents=contents, config=config
    )
    text = resp.text
    usage = resp.usage_metadata
    prompt_tokens = usage.prompt_token_count if usage else 0
    completion_tokens = usage.candidates_token_count if usage else 0
    _accum_gen(prompt_tokens, completion_tokens)
    return text, prompt_tokens, completion_tokens


# ── Embeddings ────────────────────────────────────────────────────────────────


def _gemini_embed_single(text: str, settings, task_type: str = "retrieval_document") -> list[float]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    for attempt in range(5):
        try:
            _throttle_embed()
            resp = client.models.embed_content(
                model=settings.GEMINI_EMBEDDING_MODEL,
                contents=text,
                config=types.EmbedContentConfig(task_type=task_type),
            )
            if hasattr(resp, "usage_metadata") and resp.usage_metadata:
                _accum_embed(getattr(resp.usage_metadata, "prompt_token_count", 0) or 0)
            return list(resp.embeddings[0].values)
        except Exception as e:
            msg = str(e)
            if (
                "429" in msg or "quota" in msg.lower() or "RESOURCE_EXHAUSTED" in msg
            ) and attempt < 4:
                wait = 30 * (2**attempt)  # 30, 60, 120, 240 seconds
                time.sleep(wait)
                continue
            raise
    raise RuntimeError("_gemini_embed_single: exhausted retries")


def embed_query_text(text: str, settings) -> list[float]:
    """Embed a single query string for vector search (768-dim)."""
    return _gemini_embed_single(text, settings, task_type="retrieval_query")


def embed_batch_texts(texts: list[str], settings) -> list[list[float]]:
    """Embed a batch of document chunks (768-dim each)."""
    return [_gemini_embed_single(t, settings, task_type="retrieval_document") for t in texts]


# ── RAGAS wrappers ────────────────────────────────────────────────────────────


def get_ragas_llm_wrapper(settings):
    """RAGAS-compatible LangChain LLM wrapper — Gemini."""
    from langchain_google_genai import ChatGoogleGenerativeAI
    from ragas.llms import LangchainLLMWrapper

    llm = ChatGoogleGenerativeAI(
        model=settings.GEMINI_MODEL,
        google_api_key=settings.GEMINI_API_KEY,
    )
    return LangchainLLMWrapper(llm)


def get_ragas_embeddings_wrapper(settings):
    """RAGAS-compatible LangChain embeddings wrapper — Gemini."""
    from langchain_google_genai import GoogleGenerativeAIEmbeddings
    from ragas.embeddings import LangchainEmbeddingsWrapper

    emb = GoogleGenerativeAIEmbeddings(
        model=settings.GEMINI_EMBEDDING_MODEL,
        google_api_key=settings.GEMINI_API_KEY,
    )
    return LangchainEmbeddingsWrapper(emb)
