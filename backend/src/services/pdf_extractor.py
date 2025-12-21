"""PDF text extraction service using PyMuPDF."""

import logging
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


@dataclass
class PDFContent:
    """Extracted content from a PDF."""

    filename: str
    page_count: int
    text: str
    word_count: int

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("PDF contains no extractable text")


class PDFExtractor:
    """Service for extracting text content from PDF files."""

    def __init__(self, min_words: int = 100, max_words: int = 50000) -> None:
        """Initialize extractor with word limits.

        Args:
            min_words: Minimum words required for valid content
            max_words: Maximum words to extract (truncate beyond)
        """
        self.min_words = min_words
        self.max_words = max_words

    def extract(self, pdf_path: Path | str) -> PDFContent:
        """Extract text content from a PDF file.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            PDFContent with extracted text

        Raises:
            FileNotFoundError: If PDF file doesn't exist
            ValueError: If PDF is empty or has too little content
            RuntimeError: If PDF cannot be parsed
        """
        pdf_path = Path(pdf_path)

        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        if not pdf_path.suffix.lower() == ".pdf":
            raise ValueError(f"Not a PDF file: {pdf_path}")

        logger.info(f"Extracting text from: {pdf_path.name}")

        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            raise RuntimeError(f"Failed to open PDF: {e}") from e

        try:
            text_parts: list[str] = []
            total_words = 0

            for page_num, page in enumerate(doc):
                if total_words >= self.max_words:
                    logger.warning(
                        f"Truncating at page {page_num + 1}, reached {self.max_words} words"
                    )
                    break

                page_text = page.get_text("text")
                if page_text.strip():
                    text_parts.append(f"--- Page {page_num + 1} ---\n{page_text}")
                    total_words += len(page_text.split())

            full_text = "\n\n".join(text_parts)
            word_count = len(full_text.split())

            if word_count < self.min_words:
                raise ValueError(
                    f"PDF has too little content: {word_count} words "
                    f"(minimum {self.min_words} required)"
                )

            content = PDFContent(
                filename=pdf_path.name,
                page_count=len(doc),
                text=full_text,
                word_count=word_count,
            )

            logger.info(
                f"Extracted {content.word_count} words from {content.page_count} pages"
            )

            return content

        finally:
            doc.close()


# Singleton instance
_pdf_extractor: PDFExtractor | None = None


def get_pdf_extractor() -> PDFExtractor:
    """Get PDF extractor singleton."""
    global _pdf_extractor
    if _pdf_extractor is None:
        _pdf_extractor = PDFExtractor()
    return _pdf_extractor
