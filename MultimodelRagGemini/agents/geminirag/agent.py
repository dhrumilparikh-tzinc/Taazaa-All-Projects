"""
GeminiRAG ADK Agent — for `adk web` demo UI.

Exposes 5 RAG tools to a Gemini 2.5 Flash LlmAgent and sets a demo
user context so tools can access the database without HTTP auth.

Start with:
    adk web agents/ --port 8010
Then open http://localhost:8010
"""

import os
import sys

# Ensure project root is on the path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

# Set GOOGLE_API_KEY for ADK
os.environ.setdefault("GOOGLE_API_KEY", os.environ.get("GEMINI_API_KEY", ""))

from google.adk.agents import LlmAgent

# ── Demo user context ─────────────────────────────────────────────────────────
# Use the first active admin user so tools can make DB queries.
_DEMO_USER_ID = os.environ.get("ADK_DEMO_USER_ID", "c8d96321-46dc-488b-951a-1504959a10f8")

from app.agent.tools import set_agent_user_id
set_agent_user_id(_DEMO_USER_ID)

# ── Tool wrappers ─────────────────────────────────────────────────────────────

def list_documents() -> dict:
    """List all processed documents with their chunk counts and embedding stats."""
    set_agent_user_id(_DEMO_USER_ID)
    from app.agent.tools import list_documents as _list
    return _list()


def query_documents(question: str, job_ids: list[str] | None = None) -> dict:
    """
    Answer a question from the indexed documents using RAG.

    Args:
        question: Natural language question to answer.
        job_ids: Optional list of job UUIDs to restrict search to specific documents.
                 Leave empty to search across all documents.

    Returns:
        answer: Grounded answer with [n] citation markers.
        citations: List of source document references.
        confidence_gate_passed: Whether sufficient relevant context was found.
    """
    set_agent_user_id(_DEMO_USER_ID)
    from app.agent.tools import query_rag
    return query_rag(question, job_ids)


def get_job_status(job_id: str) -> dict:
    """
    Check the processing status of a document ingestion job.

    Args:
        job_id: UUID of the job to check.

    Returns:
        status: PENDING | PROCESSING | COMPLETED | FAILED
        step: Current processing step (e.g. 'embedding', 'indexing').
        chunk_count: Number of chunks embedded so far.
    """
    set_agent_user_id(_DEMO_USER_ID)
    from app.agent.tools import get_job_status as _status
    return _status(job_id)


def summarize_document(job_id: str) -> dict:
    """
    Retrieve the AI-generated structured summary for a completed document.

    Args:
        job_id: UUID of the completed job.

    Returns:
        summary: Structured summary (key topics, entities, statistics).
    """
    set_agent_user_id(_DEMO_USER_ID)
    from app.agent.tools import summarize_document as _summ
    return _summ(job_id)


# ── Agent definition ──────────────────────────────────────────────────────────

_INSTRUCTION = """You are GeminiRAG, a multimodal document intelligence assistant powered by Google Gemini.

You have 4 tools:

1. **list_documents** — show all indexed documents with chunk counts and embedding stats.
2. **query_documents** — answer questions from document content using semantic RAG retrieval with citations.
3. **get_job_status** — check the processing status of a document by job_id.
4. **summarize_document** — retrieve the structured AI summary for a document by job_id.

Behaviour rules:
- Always use **query_documents** when the user asks a factual question about document content.
- Always cite sources with [n] markers from query results.
- When a user asks "what documents do you have" or "how many files", call **list_documents**.
- If the user provides a job_id and asks about status or summary, call the appropriate tool.
- Be concise but complete. Lead with the direct answer, then cite sources.
- Never fabricate information not present in retrieved context.

You have access to 181+ processed documents including PDFs, DOCX, XLSX, and images.
"""

root_agent = LlmAgent(
    name="GeminiRAG",
    model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
    description="Multimodal document intelligence: search, summarise, and cite across 180+ indexed documents.",
    instruction=_INSTRUCTION,
    tools=[list_documents, query_documents, get_job_status, summarize_document],
)
