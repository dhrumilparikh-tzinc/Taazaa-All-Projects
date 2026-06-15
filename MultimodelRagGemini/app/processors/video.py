"""
VideoProcessor — processes video files via Gemini File API.

Pipeline (Gemini-only):
  1. Upload the video file directly to Gemini File API.
  2. Single Gemini call with a comprehensive prompt extracts:
       - Full transcript with speaker labels and timestamps
       - Visual frame descriptions (slides, charts, diagrams)
       - Combined interleaved markdown
  3. Second Gemini call produces structured summary
     (action_items, key_decisions, topics, visual_summary).

No moviepy frame extraction, no SpeechBrain diarization, no pydub splitting —
Gemini processes audio and visual tracks natively from the uploaded video file.

Supported formats: MP4, MOV, AVI, WEBM, MKV, M4V.
"""

from app.processors.audio_utils import summarise_transcript_gemini
from app.processors.base import BaseProcessor

SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".avi", ".webm", ".mkv", ".m4v"}

_VIDEO_MIME = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".m4v": "video/mp4",
}

_EXTRACTION_PROMPT = """Analyse this video comprehensively and produce a single structured Markdown document.

Structure the output as follows:

# [filename]

## Video Summary
[2-3 sentences describing the overall content of the video]

## Transcript
[Full verbatim transcript with speaker labels and timestamps.
Use ## [Speaker N at MM:SS] headings when the speaker or significant time gap occurs.
Include all spoken words exactly as said.]

## Visual Content
[For each significant visual moment — slides, charts, diagrams, text on screen,
important visual changes — add a section:
### Visual at [MM:SS]
[Description of what is shown]]

Output clean Markdown only. Be thorough and include ALL spoken words and key visuals."""


class VideoProcessor(BaseProcessor):
    def extract(self) -> str:
        return ""

    def summarise(self, text: str, db) -> dict:
        from pathlib import Path

        self.log.info("video_processor_start", filename=self.job.filename)
        ext = Path(self.job.file_path).suffix.lower()
        mime_type = _VIDEO_MIME.get(ext, "video/mp4")

        # Upload video and extract full content via Gemini
        full_markdown = self._call_gemini_file(
            file_path=self.job.file_path,
            prompt=_EXTRACTION_PROMPT,
            mime_type=mime_type,
            response_json=False,
            max_tokens=8192,
            db=db,
        )

        if not full_markdown.strip():
            full_markdown = f"# {self.job.filename}\n\n*No extractable content found.*"
        elif not full_markdown.startswith("#"):
            full_markdown = f"# {self.job.filename}\n\n{full_markdown}"

        self.log.info("video_extraction_done", chars=len(full_markdown))

        # Structured summary via second Gemini call
        summary = summarise_transcript_gemini(
            transcript_md=full_markdown,
            filename=self.job.filename,
            settings=self.settings,
            log=self.log,
            db=db,
            job=self.job,
        )

        summary["_chunk_text"] = full_markdown
        self.log.info(
            "video_processor_done",
            speaker_count=summary.get("speaker_count"),
            md_chars=len(full_markdown),
        )
        return summary
