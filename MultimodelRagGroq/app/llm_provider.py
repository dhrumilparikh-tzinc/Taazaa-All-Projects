"""
Provider-agnostic LLM and embedding factory.

Set LLM_PROVIDER=groq (default) or LLM_PROVIDER=gemini in .env to switch
between Groq (llama-3.3-70b / llama-4-scout) and Google Gemini 2.0 Flash.

IMPORTANT — embedding dimension mismatch:
  fastembed (Groq provider) → 384-dim vectors in ChromaDB
  Gemini text-embedding-004 → 768-dim vectors in ChromaDB
  Switching providers requires wiping ChromaDB and re-ingesting all documents.
  Run: py reset_and_reprocess.py  (or DELETE the chroma/ directory)

Functions
---------
call_text_llm()            text completion (JSON or plain) via Groq or Gemini
call_vision_llm()          vision completion via Groq Vision or Gemini
embed_query_text()         single-vector embed for RAG queries
embed_batch_texts()        batch embed for document chunking
get_ragas_llm_wrapper()    RAGAS-compatible LangChain LLM wrapper
get_ragas_embeddings_wrapper() RAGAS-compatible LangChain embeddings wrapper
"""

from __future__ import annotations

import base64
import json
import time

# ── Text LLM ──────────────────────────────────────────────────────────────────


def call_text_llm(
    prompt: str,
    settings,
    response_json: bool = False,
    max_tokens: int = 512,
    system_prompt: str | None = None,
) -> str | dict:
    """Call text LLM and return a string (or parsed dict when response_json=True)."""
    if getattr(settings, "LLM_PROVIDER", "groq") == "gemini":
        return _gemini_text(prompt, settings, response_json, max_tokens, system_prompt)
    return _groq_text(prompt, settings, response_json, max_tokens, system_prompt)


def _groq_text(prompt, settings, response_json, max_tokens, system_prompt):
    import groq as _groq

    client = _groq.Groq(api_key=settings.GROQ_API_KEY)
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    kwargs: dict = {
        "model": settings.GROQ_PROCESSING_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if response_json:
        kwargs["response_format"] = {"type": "json_object"}

    for attempt in range(4):
        try:
            resp = client.chat.completions.create(**kwargs)
            text = resp.choices[0].message.content
            return json.loads(text) if response_json else text
        except _groq.RateLimitError:
            if attempt < 3:
                time.sleep(30 * (attempt + 1))
                continue
            raise
        except _groq.BadRequestError:
            raise
        except _groq.APIStatusError as e:
            if e.status_code in (413, 503) and attempt < 3:
                time.sleep(30 * (attempt + 1))
                continue
            raise
    raise RuntimeError("call_text_llm: exhausted retries")


def _gemini_text(prompt, settings, response_json, max_tokens, system_prompt):
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    config = types.GenerateContentConfig(max_output_tokens=max_tokens)
    if response_json:
        config.response_mime_type = "application/json"
    if system_prompt:
        config.system_instruction = system_prompt

    contents = prompt
    for attempt in range(4):
        try:
            resp = client.models.generate_content(
                model=settings.GEMINI_MODEL, contents=contents, config=config
            )
            text = resp.text
            return json.loads(text) if response_json else text
        except Exception as e:
            if "429" in str(e) and attempt < 3:
                time.sleep(30 * (attempt + 1))
                continue
            raise
    raise RuntimeError("_gemini_text: exhausted retries")


# ── Vision LLM ────────────────────────────────────────────────────────────────


def call_vision_llm(
    prompt: str,
    image_data: bytes,
    mime_type: str,
    settings,
    response_json: bool = False,
    max_tokens: int = 2048,
) -> str | dict:
    """Call vision LLM and return a string (or parsed dict when response_json=True)."""
    if getattr(settings, "LLM_PROVIDER", "groq") == "gemini":
        return _gemini_vision(prompt, image_data, mime_type, settings, response_json, max_tokens)
    return _groq_vision(prompt, image_data, mime_type, settings, response_json, max_tokens)


def _groq_vision(prompt, image_data, mime_type, settings, response_json, max_tokens):
    import groq as _groq

    client = _groq.Groq(api_key=settings.GROQ_API_KEY)
    b64 = base64.b64encode(image_data).decode()
    kwargs: dict = {
        "model": settings.GROQ_VISION_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        "max_tokens": max_tokens,
    }
    if response_json:
        kwargs["response_format"] = {"type": "json_object"}

    for attempt in range(4):
        try:
            resp = client.chat.completions.create(**kwargs)
            text = resp.choices[0].message.content or ""
            return json.loads(text) if response_json else text
        except _groq.RateLimitError:
            if attempt < 3:
                time.sleep(30 * (attempt + 1))
                continue
            raise
        except _groq.BadRequestError:
            raise
        except _groq.APIStatusError as e:
            if e.status_code == 503 and attempt < 3:
                time.sleep(30 * (attempt + 1))
                continue
            raise
    raise RuntimeError("_groq_vision: exhausted retries")


def _gemini_vision(prompt, image_data, mime_type, settings, response_json, max_tokens):
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    config = types.GenerateContentConfig(max_output_tokens=max_tokens)
    if response_json:
        config.response_mime_type = "application/json"

    image_part = types.Part.from_bytes(data=image_data, mime_type=mime_type)
    for attempt in range(4):
        try:
            resp = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=[image_part, prompt],
                config=config,
            )
            text = resp.text
            return json.loads(text) if response_json else text
        except Exception as e:
            if "429" in str(e) and attempt < 3:
                time.sleep(30 * (attempt + 1))
                continue
            raise
    raise RuntimeError("_gemini_vision: exhausted retries")


# ── Query LLM (RAG answer generation) ─────────────────────────────────────────


def call_query_llm(
    messages: list[dict],
    settings,
    max_tokens: int = 512,
    temperature: float = 0,
) -> tuple[str, int, int]:
    """
    Call the main RAG answer LLM. Returns (answer_text, prompt_tokens, completion_tokens).
    Uses GROQ_MODEL (llama-3.3-70b) or GEMINI_MODEL based on LLM_PROVIDER.
    """
    if getattr(settings, "LLM_PROVIDER", "groq") == "gemini":
        return _gemini_query(messages, settings, max_tokens)
    return _groq_query(messages, settings, max_tokens, temperature)


def _groq_query(messages, settings, max_tokens, temperature):
    import groq as _groq

    client = _groq.Groq(api_key=settings.GROQ_API_KEY)
    resp = client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    prompt_tokens = resp.usage.prompt_tokens if resp.usage else 0
    completion_tokens = resp.usage.completion_tokens if resp.usage else 0
    return resp.choices[0].message.content, prompt_tokens, completion_tokens


def _gemini_query(messages, settings, max_tokens):
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    # Convert OpenAI-style messages to Gemini contents
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

    config = types.GenerateContentConfig(max_output_tokens=max_tokens)
    if system_text:
        config.system_instruction = system_text

    resp = client.models.generate_content(
        model=settings.GEMINI_MODEL, contents=contents, config=config
    )
    text = resp.text
    # Gemini doesn't expose token counts the same way — use 0 as placeholder
    usage = resp.usage_metadata
    prompt_tokens = usage.prompt_token_count if usage else 0
    completion_tokens = usage.candidates_token_count if usage else 0
    return text, prompt_tokens, completion_tokens


# ── Embeddings ────────────────────────────────────────────────────────────────


def embed_query_text(text: str, settings) -> list[float]:
    """Embed a single query string for vector search."""
    if getattr(settings, "LLM_PROVIDER", "groq") == "gemini":
        return _gemini_embed_single(text, settings, task_type="retrieval_query")
    from app.rag.embedder import _get_model

    return next(_get_model(settings.EMBEDDING_MODEL).query_embed(text)).tolist()


def embed_batch_texts(texts: list[str], settings) -> list[list[float]]:
    """Embed a batch of document chunks."""
    if getattr(settings, "LLM_PROVIDER", "groq") == "gemini":
        return [_gemini_embed_single(t, settings, task_type="retrieval_document") for t in texts]
    from app.rag.embedder import _get_model

    return [v.tolist() for v in _get_model(settings.EMBEDDING_MODEL).embed(texts)]


def _gemini_embed_single(text: str, settings, task_type: str = "retrieval_document") -> list[float]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    resp = client.models.embed_content(
        model=settings.GEMINI_EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(task_type=task_type),
    )
    return list(resp.embeddings[0].values)


# ── RAGAS wrappers ────────────────────────────────────────────────────────────


def get_ragas_llm_wrapper(settings):
    """RAGAS-compatible LangChain LLM wrapper (Groq or Gemini)."""
    from ragas.llms import LangchainLLMWrapper

    if getattr(settings, "LLM_PROVIDER", "groq") == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        llm = ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL,
            google_api_key=settings.GEMINI_API_KEY,
        )
    else:
        from langchain_groq import ChatGroq

        # llama-3.1-8b-instant: 500k TPD, separate quota from the RAG answer model.
        # Do NOT use GROQ_MODEL here — that exhausts the answer-generation budget.
        llm = ChatGroq(model=settings.GROQ_PROCESSING_MODEL, api_key=settings.GROQ_API_KEY, n=1)
    return LangchainLLMWrapper(llm)


def get_ragas_embeddings_wrapper(settings):
    """RAGAS-compatible LangChain embeddings wrapper (fastembed or Gemini)."""
    from ragas.embeddings import LangchainEmbeddingsWrapper

    if getattr(settings, "LLM_PROVIDER", "groq") == "gemini":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        emb = GoogleGenerativeAIEmbeddings(
            model=settings.GEMINI_EMBEDDING_MODEL,
            google_api_key=settings.GEMINI_API_KEY,
        )
    else:
        from app.evaluation.ragas_eval import _FastEmbedLangChainEmbeddings

        emb = _FastEmbedLangChainEmbeddings(settings.EMBEDDING_MODEL)
    return LangchainEmbeddingsWrapper(emb)
