from dataclasses import dataclass

import fitz

from landintel.domain.enums import DocumentExtractionStatus


@dataclass(slots=True)
class DocumentExtractionResult:
    extraction_status: DocumentExtractionStatus
    extracted_text: str | None
    page_count: int | None


def extract_pdf_text(payload: bytes) -> DocumentExtractionResult:
    try:
        with fitz.open(stream=payload, filetype="pdf") as document:
            pages = [page.get_text("text").strip() for page in document]
            extracted_text = "\n\n".join(part for part in pages if part).strip() or None
            return DocumentExtractionResult(
                extraction_status=DocumentExtractionStatus.EXTRACTED,
                extracted_text=extracted_text,
                page_count=document.page_count,
            )
    except Exception:
        return DocumentExtractionResult(
            extraction_status=DocumentExtractionStatus.FAILED,
            extracted_text=None,
            page_count=None,
        )
