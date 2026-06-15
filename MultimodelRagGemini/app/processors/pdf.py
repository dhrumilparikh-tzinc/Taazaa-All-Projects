"""
PDF file processor.

Uploads the PDF directly to the Gemini File API, then calls Gemini to extract
all content as structured Markdown (text, tables, headers).  Each page boundary
is preserved via Gemini's native PDF understanding — no pdfplumber required.

The LLM summary (title, document_type, key_points, entities) is produced by a
second Gemini call on the extracted markdown.
"""

from app.processors.base import BaseProcessor

_EXTRACTION_PROMPT = """Extract ALL content from this PDF document as structured Markdown.

Rules:
- Preserve heading hierarchy (# for titles, ## for sections, ### for subsections)
- Convert every table to a proper markdown table with | col | headers
- Include all text exactly as written — do not paraphrase or omit
- For each page, add a ## Page N heading
- Charts/diagrams: describe type, axes, key data points
- Forms: preserve field names and values

Output clean Markdown only. No preamble, no explanation, no code fences."""


class PDFProcessor(BaseProcessor):
    def extract(self) -> str:
        # Gemini File API handles extraction; real work is in summarise (needs db)
        return ""

    def summarise(self, text: str, db) -> dict:
        self.log.info("pdf_processor_start", filename=self.job.filename)

        # Step 1: extract full markdown via Gemini File API
        markdown = self._call_gemini_file(
            file_path=self.job.file_path,
            prompt=_EXTRACTION_PROMPT,
            mime_type="application/pdf",
            response_json=False,
            max_tokens=8192,
            db=db,
        )
        full_markdown = f"# {self.job.filename}\n\n{markdown}".strip() if markdown.strip() else ""
        self.log.info("pdf_extraction_done", chars=len(full_markdown))

        # Step 2: summarise the extracted markdown
        summary_text = full_markdown[:12000] if len(full_markdown) > 12000 else full_markdown
        prompt = f"""You are a document analyst. Analyse the following document text and return ONLY valid JSON.
No preamble, no markdown code blocks, just raw JSON.

Return this exact structure:
{{
  "title": "document title or filename",
  "document_type": "report|contract|invoice|proposal|other",
  "summary": "2-3 sentence summary",
  "key_points": ["point 1", "point 2"],
  "entities": ["company names, person names, product names mentioned"]
}}

Document text:
{summary_text}
"""
        summary = self._call_gemini_json(prompt, db)
        summary["_chunk_text"] = full_markdown
        return summary
