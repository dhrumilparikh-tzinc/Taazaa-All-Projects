"""
Audio file processor (MP3, WAV, M4A, AAC, FLAC, OGG, WEBM).

Pipeline (Gemini-only):
  1. Upload audio file to Gemini File API.
  2. Gemini transcribes the audio with speaker labels and timestamps.
  3. Second Gemini call extracts summary, action items, decisions, topics.

No Groq Whisper, no SpeechBrain diarization, no pydub splitting — Gemini
handles all audio formats natively up to the File API size limit (~2 GB).
"""

from app.processors.audio_utils import (
    segments_to_markdown,
    summarise_transcript_gemini,
    transcribe_audio_gemini,
)
from app.processors.base import BaseProcessor

SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".webm"}


class AudioProcessor(BaseProcessor):
    def extract(self) -> str:
        return ""

    def summarise(self, text: str, db) -> dict:
        self.log.info("audio_processor_start", filename=self.job.filename)

        # 1. Transcribe via Gemini File API
        transcript_md = transcribe_audio_gemini(
            file_path=self.job.file_path,
            settings=self.settings,
            log=self.log,
            db=db,
            job=self.job,
        )

        # 2. Wrap in heading for chunker
        md = segments_to_markdown(self.job.filename, transcript_md)

        # 3. LLM summary
        summary = summarise_transcript_gemini(
            transcript_md=transcript_md,
            filename=self.job.filename,
            settings=self.settings,
            log=self.log,
            db=db,
            job=self.job,
        )

        summary["_chunk_text"] = md
        self.log.info(
            "audio_processor_done",
            speaker_count=summary.get("speaker_count"),
            md_chars=len(md),
        )
        return summary
