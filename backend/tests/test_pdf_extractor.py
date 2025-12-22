"""Tests for PDF extraction service."""

import tempfile
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from src.services.pdf_extractor import PDFExtractor, PDFContent


def create_test_pdf(text: str, path: Path) -> Path:
    """Create a test PDF with given text."""
    c = canvas.Canvas(str(path), pagesize=letter)

    # Split text into chunks of 10 words per line
    words = text.split()
    y = 750
    line_words = []

    for word in words:
        line_words.append(word)
        if len(line_words) >= 10:
            if y < 50:
                c.showPage()
                y = 750
            c.drawString(72, y, ' '.join(line_words))
            y -= 15
            line_words = []

    # Write remaining words
    if line_words:
        if y < 50:
            c.showPage()
            y = 750
        c.drawString(72, y, ' '.join(line_words))

    c.save()
    return path


class TestPDFExtractor:
    """Test PDF extraction functionality."""

    def test_extract_valid_pdf(self, tmp_path: Path) -> None:
        """Test extracting text from a valid PDF."""
        # Create a PDF with enough content
        content = " ".join(["word"] * 150)  # 150 words
        pdf_path = create_test_pdf(content, tmp_path / "test.pdf")

        extractor = PDFExtractor(min_words=100)
        result = extractor.extract(pdf_path)

        assert isinstance(result, PDFContent)
        assert result.page_count >= 1
        assert result.word_count >= 100

    def test_extract_insufficient_content(self, tmp_path: Path) -> None:
        """Test that extraction fails for PDFs with too little content."""
        content = "Just a few words here"
        pdf_path = create_test_pdf(content, tmp_path / "short.pdf")

        extractor = PDFExtractor(min_words=100)

        with pytest.raises(ValueError, match="too little content"):
            extractor.extract(pdf_path)

    def test_extract_nonexistent_file(self) -> None:
        """Test that extraction fails for missing files."""
        extractor = PDFExtractor()

        with pytest.raises(FileNotFoundError):
            extractor.extract(Path("/nonexistent/file.pdf"))

    def test_extract_non_pdf_file(self, tmp_path: Path) -> None:
        """Test that extraction fails for non-PDF files."""
        txt_path = tmp_path / "test.txt"
        txt_path.write_text("Not a PDF")

        extractor = PDFExtractor()

        with pytest.raises(ValueError, match="Not a PDF file"):
            extractor.extract(txt_path)
