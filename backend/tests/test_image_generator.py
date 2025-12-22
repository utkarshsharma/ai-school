"""Tests for image generation service."""

import base64
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.services.image_generator import (
    ImageGenerator,
    ImageGenerationError,
    get_image_generator,
)
from src.schemas.timeline import Timeline, TimelineSegment, Slide


def create_mock_timeline(num_segments: int = 3) -> Timeline:
    """Create a mock timeline for testing."""
    segments = []
    start_time = 0.0
    segment_duration = 60.0

    for i in range(num_segments):
        segment = TimelineSegment(
            segment_id=f"seg_{i + 1:03d}",
            start_time_seconds=start_time,
            duration_seconds=segment_duration,
            slide=Slide(
                title=f"Slide {i + 1} Title",
                bullets=[f"Point {i + 1}.1", f"Point {i + 1}.2"],
                visual_prompt=f"Clean minimalist background for slide {i + 1}",
            ),
            narration_text=(
                f"This is the narration for slide {i + 1}. "
                "It contains enough words to pass validation. "
                "Teachers will learn important concepts. "
                "Additional details for comprehensive coverage. "
                "Students benefit from structured content."
            ),
        )
        segments.append(segment)
        start_time += segment_duration

    return Timeline(
        version="1.0",
        title="Test Timeline",
        topic_summary="A test timeline for unit testing image generation functionality.",
        target_age_group="10-12 years",
        total_duration_seconds=num_segments * segment_duration,
        segments=segments,
    )


class TestImageGenerator:
    """Tests for ImageGenerator service."""

    @pytest.fixture
    def mock_storage(self, tmp_path: Path) -> MagicMock:
        """Create mock storage service."""
        storage = MagicMock()
        storage.save_image.return_value = tmp_path / "image.png"
        return storage

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        """Create mock settings."""
        settings = MagicMock()
        settings.gemini_api_key = "test-api-key"
        return settings

    def test_init_requires_api_key(self, mock_storage: MagicMock) -> None:
        """Test that initialization requires API key."""
        mock_settings = MagicMock()
        mock_settings.gemini_api_key = None

        with patch("src.services.image_generator.get_settings", return_value=mock_settings):
            with pytest.raises(ImageGenerationError) as exc_info:
                ImageGenerator(mock_storage)

            assert "GEMINI_API_KEY not configured" in str(exc_info.value)

    def test_generate_images_success(
        self,
        mock_storage: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Test successful image generation."""
        timeline = create_mock_timeline(num_segments=3)

        # Mock the Gemini response with image data
        mock_response = MagicMock()
        mock_candidate = MagicMock()
        mock_part = MagicMock()
        mock_inline_data = MagicMock()
        mock_inline_data.mime_type = "image/png"
        mock_inline_data.data = base64.b64encode(b"fake image data")
        mock_part.inline_data = mock_inline_data
        mock_candidate.content.parts = [mock_part]
        mock_response.candidates = [mock_candidate]

        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response

        with patch("src.services.image_generator.get_settings", return_value=mock_settings):
            with patch("src.services.image_generator.genai") as mock_genai:
                mock_genai.GenerativeModel.return_value = mock_model
                generator = ImageGenerator(mock_storage)
                result = generator.generate_images(timeline, "job-001")

        assert len(result) == 3
        assert "seg_001" in result
        assert "seg_002" in result
        assert "seg_003" in result
        assert mock_model.generate_content.call_count == 3

    def test_generate_images_uses_placeholder_on_failure(
        self,
        mock_storage: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Test that placeholder is used when image generation fails."""
        timeline = create_mock_timeline(num_segments=3)

        # Mock empty response (no image data)
        mock_response = MagicMock()
        mock_response.candidates = []

        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response

        with patch("src.services.image_generator.get_settings", return_value=mock_settings):
            with patch("src.services.image_generator.genai") as mock_genai:
                mock_genai.GenerativeModel.return_value = mock_model
                generator = ImageGenerator(mock_storage)
                result = generator.generate_images(timeline, "job-002")

        # Should still succeed with placeholder
        assert len(result) == 3
        assert "seg_001" in result
        assert "seg_002" in result
        assert "seg_003" in result

    def test_generate_images_propagates_error_on_storage_failure(
        self,
        mock_settings: MagicMock,
    ) -> None:
        """Test that storage errors are propagated."""
        timeline = create_mock_timeline(num_segments=3)

        mock_storage = MagicMock()
        mock_storage.save_image.side_effect = IOError("Disk full")

        mock_response = MagicMock()
        mock_response.candidates = []

        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response

        with patch("src.services.image_generator.get_settings", return_value=mock_settings):
            with patch("src.services.image_generator.genai") as mock_genai:
                mock_genai.GenerativeModel.return_value = mock_model
                generator = ImageGenerator(mock_storage)

                with pytest.raises(ImageGenerationError):
                    generator.generate_images(timeline, "job-003")

    def test_create_placeholder_image_returns_valid_png(
        self,
        mock_storage: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Test that placeholder image is a valid PNG."""
        with patch("src.services.image_generator.get_settings", return_value=mock_settings):
            with patch("src.services.image_generator.genai"):
                generator = ImageGenerator(mock_storage)
                placeholder = generator._create_placeholder_image("Test Title")

        # Check PNG magic number
        assert placeholder[:8] == b"\x89PNG\r\n\x1a\n"


class TestGetImageGenerator:
    """Tests for get_image_generator factory function."""

    def test_returns_image_generator(self) -> None:
        """Test that factory returns ImageGenerator instance."""
        mock_storage = MagicMock()
        mock_settings = MagicMock()
        mock_settings.gemini_api_key = "test-key"

        with patch("src.services.image_generator.get_settings", return_value=mock_settings):
            with patch("src.services.image_generator.genai"):
                generator = get_image_generator(mock_storage)

        assert isinstance(generator, ImageGenerator)
