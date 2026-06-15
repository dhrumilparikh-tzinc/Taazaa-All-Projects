"""
Audio transcription and summarisation via Gemini File API.

Transcription: upload audio file to Gemini File API → generate_content with a
structured transcription prompt → parse speaker-labelled segments.

Summarisation: second Gemini call on the transcript text → structured JSON
summary (action_items, key_decisions, topics, speakers).

Supported formats: MP3, WAV, M4A, AAC, FLAC, OGG, WEBM (all natively supported
by the Gemini File API — no conversion or splitting needed).
"""

import json
import time
from pathlib import Path

from app.observability.logging import log_llm_call
from app.processors.base import InvalidInputError, RateLimitError

_AUDIO_MIME = {
    ".mp3": "audio/mpeg",
    ".mp4": "audio/mp4",
    ".m4a": "audio/mp4",
    ".wav": "audio/wav",
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
    ".mpeg": "audio/mpeg",
    ".mpga": "audio/mpeg",
}

_TRANSCRIPTION_PROMPT = """Transcribe this audio recording completely and accurately.

Format the output as a structured transcript:
- Use ## [Speaker N at MM:SS] headings when the speaker changes (e.g. ## [Speaker 1 at 00:00])
- If there is only one speaker, use ## [Speaker 1 at MM:SS]
- Identify distinct speakers as Speaker 1, Speaker 2, etc.
- Include all spoken words — do not summarise or paraphrase
- Group consecutive lines from the same speaker under one heading

Output clean Markdown only. No preamble, no explanation."""

_SUMMARY_SYSTEM = """You are a meeting intelligence assistant. Given a transcript, extract structured metadata.
Return ONLY valid JSON with these keys:
{
  "summary": "2-3 sentence overview",
  "action_items": ["action 1", "action 2"],
  "key_decisions": ["decision 1"],
  "topics_discussed": ["topic 1", "topic 2"],
  "duration_seconds": 0,
  "speaker_count": 1,
  "speakers": ["Speaker 1"]
}
No preamble, no markdown fences."""


def transcribe_audio_gemini(
    file_path: str,
    settings,
    log,
    db,
    job,
) -> str:
    """
    Transcribe audio via Gemini File API.
    Returns raw transcript markdown string.
    """
    from google import genai
    from google.genai import types

    ext = Path(file_path).suffix.lower()
    mime_type = _AUDIO_MIME.get(ext, "audio/mpeg")

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    log.info("gemini_audio_upload_start", filename=Path(file_path).name)
    uploaded = client.files.upload(
        file=file_path,
        config=types.UploadFileConfig(mime_type=mime_type),
    )

    # Wait for server-side processing
    for _ in range(40):
        state = str(uploaded.state)
        if "PROCESSING" not in state:
            break
        time.sleep(4)
        uploaded = client.files.get(name=uploaded.name)

    if "FAILED" in str(uploaded.state):
        raise InvalidInputError(
            f"400: Gemini File API failed to process audio: {Path(file_path).name}"
        )

    log.info("gemini_audio_upload_done", name=uploaded.name)

    start_t = time.time()
    transcript_md = ""
    try:
        for attempt in range(4):
            try:
                resp = client.models.generate_content(
                    model=settings.GEMINI_MODEL,
                    contents=[uploaded, _TRANSCRIPTION_PROMPT],
                    config=types.GenerateContentConfig(max_output_tokens=8192),
                )
                transcript_md = resp.text or ""
                break
            except Exception as e:
                msg = str(e).lower()
                if ("429" in msg or "rate" in msg or "quota" in msg) and attempt < 3:
                    wait = 30 * (attempt + 1)
                    log.warning("gemini_audio_rate_limit", attempt=attempt, wait_s=wait)
                    time.sleep(wait)
                    continue
                raise RateLimitError(f"Gemini audio transcription failed: {e}") from e
    finally:
        try:
            client.files.delete(name=uploaded.name)
        except Exception:
            pass

    latency_ms = int((time.time() - start_t) * 1000)
    log_llm_call(
        user_id=job.user_id,
        job_id=job.id,
        endpoint="audio_transcription",
        model=settings.GEMINI_MODEL,
        prompt_tokens=0,
        completion_tokens=len(transcript_md.split()),
        latency_ms=latency_ms,
        query_text=job.filename,
        llm_response_preview=transcript_md[:500],
        db=db,
    )
    log.info("gemini_audio_transcription_done", chars=len(transcript_md))
    return transcript_md


def summarise_transcript_gemini(
    transcript_md: str,
    filename: str,
    settings,
    log,
    db,
    job,
) -> dict:
    """
    Call Gemini to extract summary, action items, decisions, and topics from transcript.
    Returns structured dict.
    """
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    if len(transcript_md) > 12000:
        transcript_md = transcript_md[:12000] + "\n...[truncated]"

    prompt = f"File: {filename}\n\nTranscript:\n{transcript_md}"

    start_t = time.time()
    result_text = "{}"
    for attempt in range(4):
        try:
            resp = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=1024,
                    response_mime_type="application/json",
                    system_instruction=_SUMMARY_SYSTEM,
                ),
            )
            result_text = resp.text or "{}"
            break
        except Exception as e:
            msg = str(e).lower()
            if ("429" in msg or "rate" in msg or "quota" in msg) and attempt < 3:
                time.sleep(30 * (attempt + 1))
                continue
            raise RateLimitError(f"Gemini transcript summary failed: {e}") from e

    latency_ms = int((time.time() - start_t) * 1000)
    log_llm_call(
        user_id=job.user_id,
        job_id=job.id,
        endpoint="transcript_summary",
        model=settings.GEMINI_MODEL,
        prompt_tokens=0,
        completion_tokens=0,
        latency_ms=latency_ms,
        query_text=filename,
        llm_response_preview=result_text[:500],
        db=db,
    )

    try:
        result = json.loads(result_text)
    except json.JSONDecodeError:
        log.warning("transcript_summary_json_failed", raw=result_text[:500])
        result = {}

    result.setdefault("summary", f"Transcript of {filename}.")
    result.setdefault("action_items", [])
    result.setdefault("key_decisions", [])
    result.setdefault("topics_discussed", [])
    result.setdefault("duration_seconds", 0)
    result.setdefault("speaker_count", 1)
    result.setdefault("speakers", ["Speaker 1"])
    return result


def segments_to_markdown(filename: str, transcript_md: str) -> str:
    """Wrap raw Gemini transcript markdown under a top-level filename heading."""
    if not transcript_md.strip():
        return f"# {filename}\n\n*No transcribable content found.*"
    if transcript_md.startswith("#"):
        return transcript_md
    return f"# {filename}\n\n{transcript_md}"
