"""Tests for content generation service."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.services.content_generator import (
    ContentGenerator,
    ContentGenerationError,
    get_content_generator,
)
from src.services.pdf_extractor import PDFContent
from src.clients.gemini import GeminiError


def create_valid_timeline_data(num_segments: int = 3, segment_duration: float = 60.0) -> dict:
    """Create valid timeline data for testing."""
    segments = []
    start_time = 0.0

    for i in range(num_segments):
        segment = {
            "segment_id": f"seg_{i + 1:03d}",
            "start_time_seconds": start_time,
            "duration_seconds": segment_duration,
            "slide": {
                "title": f"Slide {i + 1}: Topic Title",
                "bullets": [f"Key point {i + 1}.1", f"Key point {i + 1}.2"],
                "visual_prompt": f"A clean, minimalist educational slide background for slide {i + 1}.",
            },
            "narration_text": (
                f"This is the narration for slide {i + 1}. "
                "It contains enough words to pass validation requirements. "
                "The teacher will explain key concepts clearly and concisely. "
                "This helps ensure proper pedagogical communication. "
                "Additional context and examples make learning more engaging. "
                "Students benefit from clear explanations and structured content."
            ),
        }
        segments.append(segment)
        start_time += segment_duration

    return {
        "version": "1.0",
        "title": "Teacher Training: Educational Topic",
        "topic_summary": (
            "This video covers important teaching strategies for educators. "
            "It includes practical examples and evidence-based approaches."
        ),
        "target_age_group": "10-12 years",
        "total_duration_seconds": num_segments * segment_duration,
        "segments": segments,
    }


class TestContentGenerator:
    """Tests for ContentGenerator service."""

    @pytest.fixture
    def mock_storage(self, tmp_path: Path) -> MagicMock:
        """Create mock storage service."""
        storage = MagicMock()
        storage.save_timeline.return_value = tmp_path / "timeline.json"
        storage.get_timeline_path.return_value = tmp_path / "timeline.json"
        return storage

    @pytest.fixture
    def mock_gemini_client(self) -> MagicMock:
        """Create mock Gemini client."""
        client = MagicMock()
        client.generate_timeline.return_value = create_valid_timeline_data()
        return client

    def test_generate_timeline_success(
        self,
        mock_storage: MagicMock,
        mock_gemini_client: MagicMock,
    ) -> None:
        """Test successful timeline generation."""
        with patch("src.services.content_generator.get_gemini_client", return_value=mock_gemini_client):
            generator = ContentGenerator(mock_storage)
            pdf_content = PDFContent(
                filename="test.pdf",
                page_count=5,
                text="Test content " * 100,
                word_count=200,
            )

            timeline = generator.generate_timeline(pdf_content, "job-001")

            assert timeline is not None
            assert len(timeline.segments) == 3
            assert timeline.total_duration_seconds == 180.0
            mock_gemini_client.generate_timeline.assert_called_once()
            mock_storage.save_timeline.assert_called_once()

    def test_generate_timeline_gemini_error(
        self,
        mock_storage: MagicMock,
        mock_gemini_client: MagicMock,
    ) -> None:
        """Test that Gemini errors are wrapped in ContentGenerationError."""
        mock_gemini_client.generate_timeline.side_effect = GeminiError("API error")

        with patch("src.services.content_generator.get_gemini_client", return_value=mock_gemini_client):
            generator = ContentGenerator(mock_storage)
            pdf_content = PDFContent(
                filename="test.pdf",
                page_count=1,
                text="Test content " * 100,
                word_count=200,
            )

            with pytest.raises(ContentGenerationError) as exc_info:
                generator.generate_timeline(pdf_content, "job-002")

            assert "Gemini generation failed" in str(exc_info.value)

    def test_generate_timeline_eval_failure(
        self,
        mock_storage: MagicMock,
        mock_gemini_client: MagicMock,
    ) -> None:
        """Test that eval failures are wrapped in ContentGenerationError."""
        # Return invalid timeline data (missing required fields)
        mock_gemini_client.generate_timeline.return_value = {"invalid": "data"}

        with patch("src.services.content_generator.get_gemini_client", return_value=mock_gemini_client):
            generator = ContentGenerator(mock_storage)
            pdf_content = PDFContent(
                filename="test.pdf",
                page_count=1,
                text="Test content " * 100,
                word_count=200,
            )

            with pytest.raises(ContentGenerationError) as exc_info:
                generator.generate_timeline(pdf_content, "job-003")

            assert "validation failed" in str(exc_info.value)

    def test_generate_timeline_persists_json(
        self,
        mock_storage: MagicMock,
        mock_gemini_client: MagicMock,
    ) -> None:
        """Test that timeline JSON is persisted."""
        with patch("src.services.content_generator.get_gemini_client", return_value=mock_gemini_client):
            generator = ContentGenerator(mock_storage)
            pdf_content = PDFContent(
                filename="test.pdf",
                page_count=1,
                text="Test content " * 100,
                word_count=200,
            )

            generator.generate_timeline(pdf_content, "job-004")

            # Check that save_timeline was called with valid JSON
            mock_storage.save_timeline.assert_called_once()
            call_args = mock_storage.save_timeline.call_args
            assert call_args[0][0] == "job-004"  # job_id
            # Verify it's valid JSON by checking it can be parsed
            import json
            json.loads(call_args[0][1])  # Should not raise

    def test_generate_timeline_passes_correct_params(
        self,
        mock_storage: MagicMock,
        mock_gemini_client: MagicMock,
    ) -> None:
        """Test that correct parameters are passed to Gemini."""
        with patch("src.services.content_generator.get_gemini_client", return_value=mock_gemini_client):
            generator = ContentGenerator(mock_storage)
            pdf_content = PDFContent(
                filename="curriculum.pdf",
                page_count=10,
                text="Detailed curriculum content here " * 100,
                word_count=500,
            )

            generator.generate_timeline(pdf_content, "job-005")

            mock_gemini_client.generate_timeline.assert_called_once_with(
                pdf_content=pdf_content.text,
                filename="curriculum.pdf",
                job_id="job-005",
            )


class TestGetContentGenerator:
    """Tests for get_content_generator factory function."""

    def test_returns_content_generator(self) -> None:
        """Test that factory returns ContentGenerator instance."""
        mock_storage = MagicMock()

        with patch("src.services.content_generator.get_gemini_client"):
            generator = get_content_generator(mock_storage)

        assert isinstance(generator, ContentGenerator)
