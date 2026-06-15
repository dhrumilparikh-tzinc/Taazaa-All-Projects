from typing import Any, Dict, List

from google import genai

from config import GEMINI_MODEL, get_required_setting
from rag.models import AnswerResult
from rag.retriever import retrieve


SYSTEM_PROMPT = (
    "You are a helpful medical question answering assistant. "
    "Answer using only the retrieved context. "
    "If the context is insufficient, say so plainly."
)


def _build_prompt(question: str, chunks: List[Dict[str, Any]]) -> str:
    context_blocks = []
    for idx, chunk in enumerate(chunks, start=1):
        metadata = chunk.get("metadata", {})
        source = metadata.get("source", "unknown")
        category = metadata.get("category", "unknown")
        context_blocks.append(
            f"[Chunk {idx} | source={source} | category={category}]\n{chunk['text']}"
        )
    context = "\n\n".join(context_blocks)

    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"Question:\n{question}\n\n"
        f"Retrieved context:\n{context}\n\n"
        "Write a concise answer grounded in the retrieved context."
    )


def generate_answer(question: str, k: int = 5) -> Dict[str, Any]:
    cleaned_question = question.strip()
    if not cleaned_question:
        raise ValueError("question must be a non-empty string")

    chunks = retrieve(cleaned_question, k=k)
    if not chunks:
        return AnswerResult(
            question=cleaned_question,
            answer="I could not find any relevant context in the FAISS index.",
            chunks=[],
        ).__dict__

    client = genai.Client(api_key=get_required_setting("GEMINI_API_KEY"))
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=_build_prompt(cleaned_question, chunks),
    )
    answer_text = getattr(response, "text", None) or "No answer was returned by the model."

    return AnswerResult(
        question=cleaned_question,
        answer=answer_text.strip(),
        chunks=chunks,
    ).__dict__
