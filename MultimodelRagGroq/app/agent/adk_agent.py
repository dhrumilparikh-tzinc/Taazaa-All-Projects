"""
Google ADK Agent wrapping the 5 GeminiRAG tools.

The ADK LlmAgent handles autonomous tool chaining — e.g. a single instruction
"ingest /path/to/file.pdf then summarise it" will autonomously:
  1. Call ingest_file() → receive job_id
  2. Poll get_job_status() until COMPLETED
  3. Call summarize_document() → return structured summary

Usage (programmatic):
    from app.agent.adk_agent import geminirag_agent, run_adk_agent
    result = run_adk_agent("List all documents", user_id="<uuid>")

Usage (via API):
    POST /v1/agent/chat   — uses the existing Groq agent (agent.py)
    POST /v1/agent/adk    — uses this ADK agent (requires GEMINI_API_KEY)

The ADK agent requires LLM_PROVIDER=gemini or a GEMINI_API_KEY set in .env.
Falls back to None if google-adk is not installed.
"""

from __future__ import annotations

import os
from typing import Any

from app.observability.logging import get_logger

log = get_logger()

# ── Attempt ADK import ────────────────────────────────────────────────────────

try:
    from google.adk.agents import LlmAgent
    from google.adk.artifacts import InMemoryArtifactService
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    _ADK_AVAILABLE = True
except ImportError:
    _ADK_AVAILABLE = False
    log.warning("adk_not_installed", hint="pip install google-adk>=0.3.0")

# ── Tool wrappers (ADK expects plain callables with typed signatures) ─────────


def _ingest_file_tool(file_path: str) -> dict:
    """Submit a file for processing. Returns job_id."""
    from app.agent.tools import ingest_file

    return ingest_file(file_path)


def _get_job_status_tool(job_id: str) -> dict:
    """Check the processing status of a job."""
    from app.agent.tools import get_job_status

    return get_job_status(job_id)


def _query_rag_tool(question: str, job_ids: list[str] | None = None) -> dict:
    """Answer a question from ingested documents. job_ids filters to specific docs."""
    from app.agent.tools import query_rag

    return query_rag(question, job_ids)


def _list_documents_tool() -> dict:
    """List all processed documents with chunk counts."""
    from app.agent.tools import list_documents

    return list_documents()


def _summarize_document_tool(job_id: str) -> dict:
    """Retrieve the structured summary for a completed document."""
    from app.agent.tools import summarize_document

    return summarize_document(job_id)


_TOOLS = [
    _ingest_file_tool,
    _get_job_status_tool,
    _query_rag_tool,
    _list_documents_tool,
    _summarize_document_tool,
]

_AGENT_INSTRUCTION = """You are GeminiRAG, a document intelligence assistant.
You have access to five tools:
- ingest_file: submit a file path for processing; returns a job_id
- get_job_status: check if a job is PENDING, PROCESSING, COMPLETED, or FAILED
- query_rag: answer questions from ingested documents with cited evidence
- list_documents: show all processed documents and chunk statistics
- summarize_document: retrieve the AI-generated summary for a document by job_id

When asked to ingest and then summarise a document, autonomously:
1. Call ingest_file to get a job_id
2. Poll get_job_status until status == COMPLETED (check at most 30 times)
3. Call summarize_document with the job_id

Always cite [n] references in answers from query_rag.
If a document is still processing, tell the user the current step and job_id.
"""


def _build_agent():
    if not _ADK_AVAILABLE:
        return None
    from app.config import settings

    if not settings.GEMINI_API_KEY:
        log.warning("adk_agent_no_gemini_key", hint="Set GEMINI_API_KEY in .env")
        return None
    os.environ["GOOGLE_API_KEY"] = settings.GEMINI_API_KEY
    return LlmAgent(
        name="GeminiRAG",
        model=settings.GEMINI_MODEL,
        description="Multimodal document intelligence: ingest, search, summarise.",
        instruction=_AGENT_INSTRUCTION,
        tools=_TOOLS,
    )


# Module-level singleton — built lazily on first call
_agent_instance = None


def get_adk_agent():
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = _build_agent()
    return _agent_instance


def run_adk_agent(message: str, user_id: str, session_id: str | None = None) -> dict[str, Any]:
    """
    Run the ADK agent for a single turn.

    Returns {"response": str, "tool_calls": [...]} on success,
    or {"error": str, "fallback": True} if ADK is unavailable.
    """
    # Set user context for tool calls
    from app.agent.tools import set_agent_user_id

    token = set_agent_user_id(user_id)

    agent = get_adk_agent()
    if agent is None:
        # Graceful fallback to existing Groq agent
        from app.agent.agent import run_agent

        return {"response": run_agent(message, user_id, session_id), "fallback": True}

    try:
        session_service = InMemorySessionService()
        artifact_service = InMemoryArtifactService()
        runner = Runner(
            agent=agent,
            session_service=session_service,
            artifact_service=artifact_service,
        )
        sid = session_id or f"session-{user_id}"
        session_service.create_session(app_name="GeminiRAG", user_id=user_id, session_id=sid)

        tool_calls = []
        response_text = ""
        for event in runner.run(user_id=user_id, session_id=sid, new_message=message):
            if hasattr(event, "tool_call") and event.tool_call:
                tool_calls.append(
                    {
                        "tool": event.tool_call.name,
                        "args": event.tool_call.args,
                    }
                )
            if hasattr(event, "response") and event.response:
                response_text = event.response.text or response_text

        log.info("adk_agent_run", user_id=user_id, tool_calls=len(tool_calls))
        return {"response": response_text, "tool_calls": tool_calls, "fallback": False}

    except Exception as exc:
        log.error("adk_agent_error", error=str(exc))
        # Graceful fallback
        from app.agent.agent import run_agent

        return {
            "response": run_agent(message, user_id, session_id),
            "fallback": True,
            "error": str(exc),
        }
