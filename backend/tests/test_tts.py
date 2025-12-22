"""Tests for TTS (text-to-speech) service."""

import base64
from pathlib import Path
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

import pytest

from src.services.tts import (
    TTSService,
    TTSError,
    AudioSegment,
    get_tts_service,
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
        topic_summary="A test timeline for unit testing TTS functionality.",
        target_age_group="10-12 years",
        total_duration_seconds=num_segments * segment_duration,
        segments=segments,
    )


class TestTTSService:
    """Tests for TTSService."""

    @pytest.fixture
    def mock_storage(self, tmp_path: Path) -> MagicMock:
        """Create mock storage service."""
        storage = MagicMock()
        storage.save_audio.return_value = tmp_path / "audio.mp3"
        return storage

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        """Create mock settings."""
        settings = MagicMock()
        settings.google_tts_api_key = "test-tts-api-key"
        return settings

    def test_init_requires_api_key(self, mock_storage: MagicMock) -> None:
        """Test that initialization requires API key."""
        mock_settings = MagicMock()
        mock_settings.google_tts_api_key = None

        with patch("src.services.tts.get_settings", return_value=mock_settings):
            with pytest.raises(TTSError) as exc_info:
                TTSService(mock_storage)

            assert "GOOGLE_TTS_API_KEY not configured" in str(exc_info.value)

    def test_generate_audio_success(
        self,
        mock_storage: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Test successful audio generation."""
        timeline = create_mock_timeline(num_segments=3)

        # Mock successful TTS response
        mock_audio_content = base64.b64encode(b"fake audio data").decode()

        with patch("src.services.tts.get_settings", return_value=mock_settings):
            with patch("src.services.tts.httpx.Client") as mock_client:
                mock_response = MagicMock()
                mock_response.json.return_value = {"audioContent": mock_audio_content}
                mock_response.raise_for_status = MagicMock()
                mock_client.return_value.__enter__.return_value.post.return_value = mock_response

                service = TTSService(mock_storage)
                result = service.generate_audio(timeline, "job-001")

        assert len(result) == 3
        assert all(isinstance(seg, AudioSegment) for seg in result)
        assert result[0].segment_id == "seg_001"
        assert result[1].segment_id == "seg_002"
        assert result[2].segment_id == "seg_003"

    def test_generate_audio_api_error(
        self,
        mock_storage: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Test handling of API errors."""
        import httpx

        timeline = create_mock_timeline(num_segments=3)

        with patch("src.services.tts.get_settings", return_value=mock_settings):
            with patch("src.services.tts.httpx.Client") as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 500
                mock_response.text = "Internal Server Error"
                mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                    "Server error", request=MagicMock(), response=mock_response
                )
                mock_client.return_value.__enter__.return_value.post.return_value = mock_response

                service = TTSService(mock_storage)

                with pytest.raises(TTSError) as exc_info:
                    service.generate_audio(timeline, "job-002")

                assert "TTS API error" in str(exc_info.value)

    def test_generate_audio_timeout(
        self,
        mock_storage: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Test handling of timeout errors."""
        import httpx

        timeline = create_mock_timeline(num_segments=3)

        with patch("src.services.tts.get_settings", return_value=mock_settings):
            with patch("src.services.tts.httpx.Client") as mock_client:
                mock_client.return_value.__enter__.return_value.post.side_effect = (
                    httpx.TimeoutException("Request timed out")
                )

                service = TTSService(mock_storage)

                with pytest.raises(TTSError) as exc_info:
                    service.generate_audio(timeline, "job-003")

                assert "timed out" in str(exc_info.value)

    def test_generate_audio_empty_response(
        self,
        mock_storage: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Test handling of empty audio response."""
        timeline = create_mock_timeline(num_segments=3)

        with patch("src.services.tts.get_settings", return_value=mock_settings):
            with patch("src.services.tts.httpx.Client") as mock_client:
                mock_response = MagicMock()
                mock_response.json.return_value = {}  # No audioContent
                mock_response.raise_for_status = MagicMock()
                mock_client.return_value.__enter__.return_value.post.return_value = mock_response

                service = TTSService(mock_storage)

                with pytest.raises(TTSError) as exc_info:
                    service.generate_audio(timeline, "job-004")

                assert "No audio content" in str(exc_info.value)

    def test_audio_segment_dataclass(self) -> None:
        """Test AudioSegment dataclass."""
        segment = AudioSegment(
            segment_id="seg_001",
            path=Path("/tmp/audio.mp3"),
            duration_seconds=45.5,
        )

        assert segment.segment_id == "seg_001"
        assert segment.path == Path("/tmp/audio.mp3")
        assert segment.duration_seconds == 45.5


class TestGetTTSService:
    """Tests for get_tts_service factory function."""

    def test_returns_tts_service(self) -> None:
        """Test that factory returns TTSService instance."""
        mock_storage = MagicMock()
        mock_settings = MagicMock()
        mock_settings.google_tts_api_key = "test-key"

        with patch("src.services.tts.get_settings", return_value=mock_settings):
            service = get_tts_service(mock_storage)

        assert isinstance(service, TTSService)
