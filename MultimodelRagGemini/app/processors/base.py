"""
Abstract base class for all file processors.

Subclasses implement two methods:
  extract()   — parse the raw file into a markdown string (no LLM call).
  summarise() — call the LLM and return a structured summary dict.

The base class provides:
  run()                  — orchestrates extract → summarise, saves extracted.md
                           to disk, persists summary to Job.result.
  _call_gemini_json()    — Gemini text LLM → parsed JSON dict.
  _call_vision_markdown()— Gemini vision LLM → plain markdown string.
  _call_gemini_vision_json() — Gemini vision LLM → parsed JSON dict.
  _call_gemini_file()    — upload a file to Gemini File API, call generate_content,
                           delete the file; returns the response text.
  _upload_to_gemini()    — upload a file and wait until ACTIVE; returns (client, file).
  _table_to_markdown()   — converts a list-of-rows table to a markdown table.

Every LLM method retries up to 4 times with 30 s × attempt back-off on
rate-limit errors, and raises InvalidInputError immediately on 400 BadRequest.
"""

import json
import time
from abc import ABC, abstractmethod
from pathlib import Path

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
        chunk_override = summary.pop("_chunk_text", None)
        speaker_embeddings = summary.pop("_speaker_embeddings", None)
        self.job.result = json.dumps(summary)
        db.add(self.job)
        db.commit()
        if speaker_embeddings is not None:
            summary["_speaker_embeddings"] = speaker_embeddings

        chunk_text = chunk_override if chunk_override is not None else text

        if chunk_text.strip():
            md_path = Path(self.job.file_path).parent / "extracted.md"
            try:
                md_path.write_text(chunk_text, encoding="utf-8")
                self.log.info("markdown_saved", path=str(md_path), chars=len(chunk_text))
            except Exception as exc:
                self.log.warning("markdown_save_failed", error=str(exc))

        return chunk_text, summary

    # ── Gemini File API helpers ────────────────────────────────────────────────

    def _upload_to_gemini(self, file_path: str, mime_type: str | None = None):
        """Upload a file to Gemini File API and wait until ACTIVE.
        Returns (genai_client, uploaded_file).
        """
        from google import genai
        from google.genai import types as _types

        client = genai.Client(api_key=self.settings.GEMINI_API_KEY)
        upload_config = _types.UploadFileConfig(mime_type=mime_type) if mime_type else None
        uploaded = client.files.upload(file=file_path, config=upload_config)
        self.log.info("gemini_file_uploaded", name=uploaded.name, state=str(uploaded.state))

        # Poll until ACTIVE (audio/video need server-side processing)
        for _ in range(40):
            state = str(uploaded.state)
            if "PROCESSING" not in state:
                break
            time.sleep(4)
            uploaded = client.files.get(name=uploaded.name)

        if "FAILED" in str(uploaded.state):
            raise InvalidInputError(
                f"400: Gemini File API failed to process {Path(file_path).name}"
            )
        return client, uploaded

    def _call_gemini_file(
        self,
        file_path: str,
        prompt: str,
        mime_type: str | None = None,
        response_json: bool = False,
        max_tokens: int = 4096,
        db=None,
    ) -> str | dict:
        """Upload file to Gemini File API, generate content, delete file. Returns text or dict."""
        from google.genai import types

        client, uploaded_file = self._upload_to_gemini(file_path, mime_type)
        config = types.GenerateContentConfig(max_output_tokens=max_tokens)
        if response_json:
            config.response_mime_type = "application/json"

        start = time.time()
        try:
            for attempt in range(5):
                try:
                    from app.llm_provider import _accum_gen, _throttle_gen

                    _throttle_gen()
                    resp = client.models.generate_content(
                        model=self.settings.GEMINI_MODEL,
                        contents=[uploaded_file, prompt],
                        config=config,
                    )
                    text = resp.text or ""
                    if resp.usage_metadata:
                        _accum_gen(
                            resp.usage_metadata.prompt_token_count or 0,
                            resp.usage_metadata.candidates_token_count or 0,
                        )
                    break
                except Exception as e:
                    msg = str(e)
                    if (
                        "429" in msg or "quota" in msg.lower() or "RESOURCE_EXHAUSTED" in msg
                    ) and attempt < 4:
                        wait = 60 * (2**attempt)  # 60, 120, 240, 480 seconds
                        self.log.warning(
                            "gemini_rate_limit_retry", attempt=attempt + 1, wait_s=wait
                        )
                        time.sleep(wait)
                        continue
                    raise
            else:
                raise RuntimeError("_call_gemini_file: exhausted retries")
        finally:
            # Always clean up the uploaded file
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception:
                pass

        latency_ms = int((time.time() - start) * 1000)
        if db is not None:
            _pt = resp.usage_metadata.prompt_token_count if resp.usage_metadata else 0
            _ct = resp.usage_metadata.candidates_token_count if resp.usage_metadata else 0
            log_llm_call(
                user_id=self.job.user_id,
                job_id=self.job.id,
                endpoint=f"{self.job.file_type}_processor",
                model=self.settings.GEMINI_MODEL,
                prompt_tokens=_pt or 0,
                completion_tokens=_ct or 0,
                latency_ms=latency_ms,
                query_text=self.job.filename,
                llm_response_preview=text[:500],
                db=db,
            )

        if response_json:
            from app.llm_provider import _safe_parse_json

            result = _safe_parse_json(text)
            if not result:
                self.log.warning("gemini_file_json_parse_failed", raw=text[:500])
            return result
        return text

    # ── Text / vision LLM helpers (routing through llm_provider) ──────────────

    def _call_gemini_json(self, prompt: str, db) -> dict:
        """Gemini text LLM call — returns parsed JSON dict."""
        from app.llm_provider import call_text_llm

        start = time.time()
        try:
            result = call_text_llm(prompt, self.settings, response_json=True, max_tokens=1024)
        except Exception as e:
            msg = str(e).lower()
            if "429" in msg or "rate" in msg or "quota" in msg:
                raise RateLimitError(f"429: LLM rate limit — {e}") from e
            if "400" in msg or "invalid" in msg:
                raise InvalidInputError(f"400: LLM invalid argument — {e}") from e
            raise
        latency_ms = int((time.time() - start) * 1000)
        log_llm_call(
            user_id=self.job.user_id,
            job_id=self.job.id,
            endpoint=f"{self.job.file_type}_processor",
            model=self.settings.GEMINI_MODEL,
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=latency_ms,
            query_text=self.job.filename,
            llm_response_preview=str(result)[:500],
            db=db,
        )
        return result

    def _call_vision_markdown(self, prompt: str, image_data: bytes, mime_type: str, db) -> str:
        """Gemini vision LLM call — returns plain markdown text."""
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
        log_llm_call(
            user_id=self.job.user_id,
            job_id=self.job.id,
            endpoint="image_processor",
            model=self.settings.GEMINI_MODEL,
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=latency_ms,
            query_text=self.job.filename,
            llm_response_preview=text[:500],
            db=db,
        )
        return text

    def _call_gemini_vision_json(self, prompt: str, image_data: bytes, mime_type: str, db) -> dict:
        """Gemini vision LLM call — returns parsed JSON dict."""
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
        log_llm_call(
            user_id=self.job.user_id,
            job_id=self.job.id,
            endpoint="image_processor",
            model=self.settings.GEMINI_MODEL,
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
