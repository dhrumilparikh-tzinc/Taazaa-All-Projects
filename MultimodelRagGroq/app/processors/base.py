"""
Abstract base class for all file processors.

Subclasses implement two methods:
  extract()   — parse the raw file into a markdown string (no LLM call).
  summarise() — call the LLM and return a structured summary dict.

The base class provides:
  run()                  — orchestrates extract → summarise, pops internal
                           keys (_chunk_text, _speaker_embeddings) before
                           persisting the summary to Job.result, then returns
                           (chunk_text, summary) to the Celery task.
  _call_gemini_json()    — Groq text LLM → parsed JSON dict (name is legacy;
                           uses GROQ_PROCESSING_MODEL).
  _call_vision_markdown()— Groq Vision LLM → plain markdown string.
  _call_gemini_vision_json() — Groq Vision LLM → parsed JSON dict.
  _table_to_markdown()   — converts a list-of-rows table to a markdown table.

Every LLM method retries up to 4 times with 30 s × attempt back-off on
RateLimitError and 503 / 413 errors, and raises InvalidInputError immediately
on 400 BadRequest.
"""

import base64
import json
import time
from abc import ABC, abstractmethod
from pathlib import Path

import groq as groq_sdk

from app.observability.logging import get_logger, log_llm_call


class RateLimitError(Exception):
    pass


class InvalidInputError(Exception):
    pass


class BaseProcessor(ABC):
    def __init__(self, job, settings):
        self.job = job
        self.settings = settings
        self.log = get_logger().bind(job_id=str(job.id), file_type=job.file_type)
        self._client = groq_sdk.Groq(api_key=settings.GROQ_API_KEY)

    @abstractmethod
    def extract(self) -> str:
        """Extract raw markdown from the file. Returns markdown string."""

    @abstractmethod
    def summarise(self, text: str, db) -> dict:
        """Call LLM and return structured summary dict.
        May include '_chunk_text' key to override what gets chunked."""

    def run(self, db) -> tuple[str, dict]:
        """Called by Celery task. Returns (markdown_for_chunking, summary_dict)."""
        text = self.extract()
        summary = self.summarise(text, db)
        # Allow processors to override chunking text via '_chunk_text' key
        chunk_override = summary.pop("_chunk_text", None)
        # Strip large internal keys before persisting to DB, then restore for the caller.
        speaker_embeddings = summary.pop("_speaker_embeddings", None)
        self.job.result = json.dumps(summary)
        db.add(self.job)
        db.commit()
        if speaker_embeddings is not None:
            summary["_speaker_embeddings"] = speaker_embeddings

        chunk_text = chunk_override if chunk_override is not None else text

        # Save markdown to disk alongside the source file
        if chunk_text.strip():
            md_path = Path(self.job.file_path).parent / "extracted.md"
            try:
                md_path.write_text(chunk_text, encoding="utf-8")
                self.log.info("markdown_saved", path=str(md_path), chars=len(chunk_text))
            except Exception as exc:
                self.log.warning("markdown_save_failed", error=str(exc))

        return chunk_text, summary

    def _call_gemini_json(self, prompt: str, db) -> dict:
        """LLM text call — returns parsed JSON dict. Routes to Groq or Gemini via LLM_PROVIDER."""
        from app.llm_provider import call_text_llm

        start = time.time()
        try:
            result = call_text_llm(prompt, self.settings, response_json=True, max_tokens=512)
        except Exception as e:
            msg = str(e).lower()
            if "429" in msg or "rate" in msg or "quota" in msg:
                raise RateLimitError(f"429: LLM rate limit — {e}") from e
            if "400" in msg or "invalid" in msg:
                raise InvalidInputError(f"400: LLM invalid argument — {e}") from e
            raise
        latency_ms = int((time.time() - start) * 1000)
        provider = getattr(self.settings, "LLM_PROVIDER", "groq")
        model = (
            self.settings.GEMINI_MODEL
            if provider == "gemini"
            else self.settings.GROQ_PROCESSING_MODEL
        )
        log_llm_call(
            user_id=self.job.user_id,
            job_id=self.job.id,
            endpoint=f"{self.job.file_type}_processor",
            model=model,
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=latency_ms,
            query_text=self.job.filename,
            llm_response_preview=str(result)[:500],
            db=db,
        )
        return result

    def _call_vision_markdown(self, prompt: str, image_data: bytes, mime_type: str, db) -> str:
        """Vision LLM call — returns plain markdown text. Routes to Groq or Gemini via LLM_PROVIDER."""
        from app.llm_provider import call_vision_llm

        start = time.time()
        try:
            text = call_vision_llm(
                prompt, image_data, mime_type, self.settings, response_json=False, max_tokens=2048
            )
        except Exception as e:
            msg = str(e).lower()
            if "429" in msg or "rate" in msg or "quota" in msg:
                raise RateLimitError(f"429: LLM rate limit — {e}") from e
            if "400" in msg or "invalid" in msg:
                raise InvalidInputError(f"400: LLM invalid argument — {e}") from e
            raise
        latency_ms = int((time.time() - start) * 1000)
        provider = getattr(self.settings, "LLM_PROVIDER", "groq")
        model = (
            self.settings.GEMINI_MODEL if provider == "gemini" else self.settings.GROQ_VISION_MODEL
        )
        log_llm_call(
            user_id=self.job.user_id,
            job_id=self.job.id,
            endpoint="image_processor",
            model=model,
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=latency_ms,
            query_text=self.job.filename,
            llm_response_preview=text[:500],
            db=db,
        )
        return text

    def _call_gemini_vision_json(self, prompt: str, image_data: bytes, mime_type: str, db) -> dict:
        """Vision LLM call — returns parsed JSON dict. Routes to Groq or Gemini via LLM_PROVIDER."""
        from app.llm_provider import call_vision_llm

        start = time.time()
        try:
            result = call_vision_llm(
                prompt, image_data, mime_type, self.settings, response_json=True, max_tokens=512
            )
        except Exception as e:
            msg = str(e).lower()
            if "429" in msg or "rate" in msg or "quota" in msg:
                raise RateLimitError(f"429: LLM rate limit — {e}") from e
            if "400" in msg or "invalid" in msg:
                raise InvalidInputError(f"400: LLM invalid argument — {e}") from e
            raise
        latency_ms = int((time.time() - start) * 1000)
        provider = getattr(self.settings, "LLM_PROVIDER", "groq")
        model = (
            self.settings.GEMINI_MODEL if provider == "gemini" else self.settings.GROQ_VISION_MODEL
        )
        log_llm_call(
            user_id=self.job.user_id,
            job_id=self.job.id,
            endpoint="image_processor",
            model=model,
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=latency_ms,
            query_text=self.job.filename,
            llm_response_preview=str(result)[:500],
            db=db,
        )
        return result

    @staticmethod
    def _table_to_markdown(rows: list[list]) -> str:
        if not rows:
            return ""
        cleaned = [[str(cell) if cell is not None else "" for cell in row] for row in rows]
        if not cleaned:
            return ""
        header = "| " + " | ".join(cleaned[0]) + " |"
        separator = "| " + " | ".join(["---"] * len(cleaned[0])) + " |"
        body_rows = ["| " + " | ".join(row) + " |" for row in cleaned[1:]]
        return "\n".join([header, separator] + body_rows)
