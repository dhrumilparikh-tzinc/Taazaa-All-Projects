"""
Gemini-powered document chat agent with Redis-backed session history.

Architecture
------------
run_agent() is the single entry point called by the /v1/agent/chat endpoint.

1. Intent classification (deterministic, no LLM):
     chitchat   — greetings and social filler → skip retrieval.
     list_docs  — "how many documents / files" → call list_documents() tool.
     job_status — message contains a UUID and status/progress keywords →
                  call get_job_status() tool.
     rag_query  — everything else → vector ChromaDB retrieval.

2. Context injection:
     The retrieved data is appended to the user message inside XML tags.
     The system prompt instructs the LLM to cite chunks and refuse to answer
     from outside the provided context.

3. Single Gemini LLM call:
     The assembled message history (system + last 10 turns + current user
     message with injected context) is sent in one request.

4. Session persistence:
     Full unbounded history is saved to Redis (SESSION_TTL = 7 days).
     Only the last 10 messages are included in the LLM window to cap
     context length. The injected context is stripped before saving.
"""

import json
import re
import uuid as _uuid
from datetime import date as _date

import redis as redis_sdk

from app.agent.tools import (
    get_job_status,
    list_documents,
    set_agent_user_id,
)
from app.config import settings
from app.observability.logging import get_logger

log = get_logger()

SESSION_TTL = 60 * 60 * 24 * 7  # 7 days
SESSION_KEY_PREFIX = "agent:session:"

_AGENT_TOP_K = 5
_CHUNK_EXCERPT = 600


# ---------------------------------------------------------------------------
# Session helpers (Redis-backed)
# ---------------------------------------------------------------------------


def _redis() -> redis_sdk.Redis:
    return redis_sdk.from_url(settings.REDIS_URL, decode_responses=True)


def _load_session(session_id: str) -> list[dict]:
    try:
        data = _redis().get(f"{SESSION_KEY_PREFIX}{session_id}")
        if data:
            return json.loads(data)
    except Exception as exc:
        log.warning("session_load_error", session_id=session_id, error=str(exc))
    return [{"role": "system", "content": SYSTEM_PROMPT}]


def _save_session(session_id: str, messages: list[dict]) -> None:
    try:
        _redis().setex(f"{SESSION_KEY_PREFIX}{session_id}", SESSION_TTL, json.dumps(messages))
    except Exception as exc:
        log.warning("session_save_error", session_id=session_id, error=str(exc))


# ---------------------------------------------------------------------------
# Vector retrieval
# ---------------------------------------------------------------------------


def _retrieve_chunks(question: str) -> tuple[list[dict], float]:
    """Vector search via Gemini embeddings. Returns (top-k chunks, top_vector_score)."""
    from app.rag.embedder import embed_query
    from app.rag.reranker import rerank
    from app.rag.vectorstore import get_chroma_client, get_or_create_collection, search

    q_emb = embed_query(question, settings)
    client = get_chroma_client(settings)
    col = get_or_create_collection(client, settings)

    chunks = search(col, q_emb, top_k=_AGENT_TOP_K * 2)
    top_vector_score = chunks[0]["score"] if chunks else 0.0
    return rerank(question, chunks, top_k=_AGENT_TOP_K), top_vector_score


def _build_context_block(chunks: list[dict]) -> str:
    parts = []
    for i, c in enumerate(chunks, 1):
        excerpt = c["text"][:_CHUNK_EXCERPT]
        parts.append(f"[{i}] {c['filename']} ({c['page_or_segment']}): {excerpt}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Intent classification — deterministic, no LLM needed
# ---------------------------------------------------------------------------

_GREETING_RE = re.compile(
    r"^(hi+|hello|hey|thanks?|thank\s+you|ok(ay)?|bye|good\s*(bye)?|great|"
    r"perfect|got\s+it|sounds\s+good|alright|sure|cool|nice|yep|nope?|yes|no|"
    r"awesome|makes\s+sense|understood)[!.,?'\s]*$",
    re.IGNORECASE,
)

_LIST_DOCS_RE = re.compile(
    r"("
    r"\b(?:list|show|what|which|how\s+many|tell\s+me|count|number\s+of|how\s+much)\b"
    r".{0,30}"
    r"\b(?:documents?|files?|uploaded|available|processed|stored|indexed|in\s+(?:the\s+)?(?:database|db|system|pipeline))\b"
    r"|"
    r"\b(?:how\s+many|what\s+is\s+the|total|count\s+of)\b.{0,20}"
    r"\b(?:chunks?|embeddings?|vectors?|embedded|indexed|pieces?)\b"
    r"|"
    r"\b(?:stats?|statistics|pipeline\s+info|system\s+info)\b"
    r")",
    re.IGNORECASE,
)

_JOB_STATUS_RE = re.compile(
    r"\bjob[_\s-]?id\b|"
    r"\b(status|progress|check).{0,20}\bjob\b|"
    r"\bjob.{0,20}(status|progress|check)\b",
    re.IGNORECASE,
)

_UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)


def _classify(message: str) -> str:
    """Returns: 'chitchat' | 'list_docs' | 'job_status' | 'rag_query'"""
    stripped = message.strip()
    if _GREETING_RE.match(stripped):
        return "chitchat"
    if _LIST_DOCS_RE.search(stripped):
        return "list_docs"
    if _JOB_STATUS_RE.search(stripped) and _UUID_RE.search(stripped):
        return "job_status"
    return "rag_query"


def _extract_uuid(text: str) -> str | None:
    m = _UUID_RE.search(text)
    return m.group(0) if m else None


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an intelligent document assistant for MasterCRM.

When document context is provided between <context> tags:
- Answer ONLY using facts explicitly stated in that context.
- Cite every claim with [n] matching the numbered source.
- If the answer is not in the context, say: "I don't have that information in the provided documents."
- Never guess, infer, or use outside knowledge.

When a <document_list> is provided:
- Report "total_documents" as the exact document count.
- Report "total_chunks_embedded" as the total embedded chunk count.
- Do NOT mention list limits, truncation, or implementation details.

Use conversation history to resolve follow-up questions.
For greetings and chitchat, respond naturally without referencing documents."""


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def run_agent(message: str, user_id: str, session_id: str | None = None) -> dict:
    if session_id is None:
        session_id = str(_uuid.uuid4())

    set_agent_user_id(user_id)

    full_history = _load_session(session_id)
    system_msg = full_history[0]
    recent = full_history[-10:] if len(full_history) > 11 else full_history[1:]
    messages = [system_msg] + recent
    messages.append({"role": "user", "content": message})

    tool_names_called: list[str] = []
    prompt_tokens = 0
    completion_tokens = 0

    intent = _classify(message)
    log.info("agent_intent", intent=intent, message_preview=message[:80])

    # -----------------------------------------------------------------------
    # Step 1 — Gather context based on intent
    # -----------------------------------------------------------------------
    context_injection = ""

    if intent == "list_docs":
        result = list_documents()
        tool_names_called.append("list_documents")
        today = _date.today().strftime("%B %d, %Y")
        context_injection = (
            f"\n\n<document_list>\n"
            f"Today's date: {today}\n"
            f"{json.dumps(result, indent=2)}\n"
            f"</document_list>"
        )

    elif intent == "job_status":
        job_id = _extract_uuid(message)
        if job_id:
            result = get_job_status(job_id)
            tool_names_called.append("get_job_status")
            context_injection = f"\n\n<job_status>\n{json.dumps(result, indent=2)}\n</job_status>"
        else:
            intent = "rag_query"

    if intent == "rag_query":
        try:
            chunks, top_vector_score = _retrieve_chunks(message)
            if chunks and top_vector_score >= settings.CONFIDENCE_THRESHOLD:
                context_block = _build_context_block(chunks)
                context_injection = f"\n\n<context>\n{context_block}\n</context>"
                tool_names_called.append("query_rag")
                log.info(
                    "agent_rag_retrieved",
                    chunks=len(chunks),
                    top_vector_score=round(top_vector_score, 4),
                )
            elif chunks:
                log.info("agent_rag_low_confidence", top_vector_score=round(top_vector_score, 4))
        except Exception as exc:
            log.error("agent_rag_error", error=str(exc)[:200])

    if context_injection:
        messages[-1] = {"role": "user", "content": message + context_injection}

    # -----------------------------------------------------------------------
    # Step 2 — Single Gemini call for synthesis
    # -----------------------------------------------------------------------
    final_text = ""
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        # Convert OpenAI-style message list to Gemini contents
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
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        if system_text:
            config.system_instruction = system_text

        resp = client.models.generate_content(
            model=settings.GEMINI_MODEL, contents=contents, config=config
        )
        final_text = resp.text or ""
        usage = resp.usage_metadata
        prompt_tokens = usage.prompt_token_count if usage else 0
        completion_tokens = usage.candidates_token_count if usage else 0

        messages[-1] = {"role": "user", "content": message}
        messages.append({"role": "assistant", "content": final_text})

    except Exception as exc:
        msg = str(exc).lower()
        if "429" in msg or "rate" in msg or "quota" in msg:
            log.warning("agent_rate_limit", error=str(exc)[:200])
            final_text = (
                "I'm hitting a rate limit right now. Please wait a few seconds and try again."
            )
        else:
            log.error("agent_synthesis_error", error=str(exc)[:300])
            final_text = "Something went wrong generating a response. Please try again."
        messages[-1] = {"role": "user", "content": message}

    # Persist full unbounded history
    full_history.append({"role": "user", "content": message})
    if (
        final_text
        and not final_text.startswith("I'm hitting")
        and not final_text.startswith("Something went wrong")
    ):
        full_history.append({"role": "assistant", "content": final_text})
    _save_session(session_id, full_history)

    log.info(
        "agent_run_complete",
        user_id=user_id,
        session_id=session_id,
        intent=intent,
        tool_call_count=len(tool_names_called),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )

    return {
        "response": final_text,
        "tool_calls_made": tool_names_called,
        "session_id": session_id,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
    }
