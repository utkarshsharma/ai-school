"""Tests for Remotion client."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.clients.remotion import (
    RemotionClient,
    RemotionError,
    get_remotion_client,
)
from src.services.tts import AudioSegment
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
        topic_summary="A test timeline for unit testing Remotion client functionality.",
        target_age_group="10-12 years",
        total_duration_seconds=num_segments * segment_duration,
        segments=segments,
    )


class TestRemotionClient:
    """Tests for RemotionClient."""

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        """Create mock settings."""
        settings = MagicMock()
        settings.remotion_service_url = "http://localhost:3000"
        return settings

    @pytest.fixture
    def mock_storage(self, tmp_path: Path) -> MagicMock:
        """Create mock storage service."""
        storage = MagicMock()
        storage.get_video_path.return_value = tmp_path / "output.mp4"
        return storage

    def test_health_check_success(self, mock_settings: MagicMock) -> None:
        """Test successful health check."""
        with patch("src.clients.remotion.get_settings", return_value=mock_settings):
            with patch("src.clients.remotion.httpx.Client") as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_client.return_value.__enter__.return_value.get.return_value = mock_response

                client = RemotionClient()
                result = client.health_check()

        assert result is True

    def test_health_check_failure(self, mock_settings: MagicMock) -> None:
        """Test health check failure."""
        with patch("src.clients.remotion.get_settings", return_value=mock_settings):
            with patch("src.clients.remotion.httpx.Client") as mock_client:
                mock_client.return_value.__enter__.return_value.get.side_effect = (
                    Exception("Connection refused")
                )

                client = RemotionClient()
                result = client.health_check()

        assert result is False

    def test_render_video_success(
        self,
        mock_settings: MagicMock,
        mock_storage: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test successful video render."""
        timeline = create_mock_timeline(num_segments=3)

        # Create audio segments
        audio_segments = [
            AudioSegment(
                segment_id="seg_001",
                path=tmp_path / "seg_001.mp3",
                duration_seconds=60.0,
            ),
            AudioSegment(
                segment_id="seg_002",
                path=tmp_path / "seg_002.mp3",
                duration_seconds=60.0,
            ),
            AudioSegment(
                segment_id="seg_003",
                path=tmp_path / "seg_003.mp3",
                duration_seconds=60.0,
            ),
        ]

        # Create image paths
        image_paths = {
            "seg_001": tmp_path / "seg_001.png",
            "seg_002": tmp_path / "seg_002.png",
            "seg_003": tmp_path / "seg_003.png",
        }

        with patch("src.clients.remotion.get_settings", return_value=mock_settings):
            with patch("src.clients.remotion.httpx.Client") as mock_client:
                mock_response = MagicMock()
                mock_response.json.return_value = {"success": True}
                mock_response.raise_for_status = MagicMock()
                mock_client.return_value.__enter__.return_value.post.return_value = mock_response

                client = RemotionClient()
                result = client.render_video(
                    job_id="job-001",
                    timeline=timeline,
                    audio_segments=audio_segments,
                    image_paths=image_paths,
                    storage=mock_storage,
                )

        assert result == tmp_path / "output.mp4"
        mock_storage.get_video_path.assert_called_once_with("job-001")

    def test_render_video_timeout(
        self,
        mock_settings: MagicMock,
        mock_storage: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test render timeout handling."""
        import httpx

        timeline = create_mock_timeline(num_segments=3)
        audio_segments = [
            AudioSegment(segment_id=f"seg_{i:03d}", path=tmp_path / f"seg_{i:03d}.mp3", duration_seconds=60.0)
            for i in range(1, 4)
        ]
        image_paths = {f"seg_{i:03d}": tmp_path / f"seg_{i:03d}.png" for i in range(1, 4)}

        with patch("src.clients.remotion.get_settings", return_value=mock_settings):
            with patch("src.clients.remotion.httpx.Client") as mock_client:
                mock_client.return_value.__enter__.return_value.post.side_effect = (
                    httpx.TimeoutException("Request timed out")
                )

                client = RemotionClient()

                with pytest.raises(RemotionError) as exc_info:
                    client.render_video(
                        job_id="job-002",
                        timeline=timeline,
                        audio_segments=audio_segments,
                        image_paths=image_paths,
                        storage=mock_storage,
                    )

                assert "timed out" in str(exc_info.value)

    def test_render_video_http_error(
        self,
        mock_settings: MagicMock,
        mock_storage: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test HTTP error handling."""
        import httpx

        timeline = create_mock_timeline(num_segments=3)
        audio_segments = [
            AudioSegment(segment_id=f"seg_{i:03d}", path=tmp_path / f"seg_{i:03d}.mp3", duration_seconds=60.0)
            for i in range(1, 4)
        ]
        image_paths = {f"seg_{i:03d}": tmp_path / f"seg_{i:03d}.png" for i in range(1, 4)}

        with patch("src.clients.remotion.get_settings", return_value=mock_settings):
            with patch("src.clients.remotion.httpx.Client") as mock_client:
                mock_response = MagicMock()
                mock_response.text = "Internal Server Error"
                mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                    "Server error", request=MagicMock(), response=mock_response
                )
                mock_client.return_value.__enter__.return_value.post.return_value = mock_response

                client = RemotionClient()

                with pytest.raises(RemotionError) as exc_info:
                    client.render_video(
                        job_id="job-003",
                        timeline=timeline,
                        audio_segments=audio_segments,
                        image_paths=image_paths,
                        storage=mock_storage,
                    )

                assert "failed" in str(exc_info.value).lower()

    def test_render_video_failure_response(
        self,
        mock_settings: MagicMock,
        mock_storage: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test handling of failure response from Remotion."""
        timeline = create_mock_timeline(num_segments=3)
        audio_segments = [
            AudioSegment(segment_id=f"seg_{i:03d}", path=tmp_path / f"seg_{i:03d}.mp3", duration_seconds=60.0)
            for i in range(1, 4)
        ]
        image_paths = {f"seg_{i:03d}": tmp_path / f"seg_{i:03d}.png" for i in range(1, 4)}

        with patch("src.clients.remotion.get_settings", return_value=mock_settings):
            with patch("src.clients.remotion.httpx.Client") as mock_client:
                mock_response = MagicMock()
                mock_response.json.return_value = {
                    "success": False,
                    "error": "Render failed due to invalid composition"
                }
                mock_response.raise_for_status = MagicMock()
                mock_client.return_value.__enter__.return_value.post.return_value = mock_response

                client = RemotionClient()

                with pytest.raises(RemotionError) as exc_info:
                    client.render_video(
                        job_id="job-004",
                        timeline=timeline,
                        audio_segments=audio_segments,
                        image_paths=image_paths,
                        storage=mock_storage,
                    )

                assert "invalid composition" in str(exc_info.value)

    def test_render_video_builds_correct_request(
        self,
        mock_settings: MagicMock,
        mock_storage: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test that render request contains correct data."""
        timeline = create_mock_timeline(num_segments=3)
        audio_segments = [
            AudioSegment(segment_id=f"seg_{i:03d}", path=tmp_path / f"seg_{i:03d}.mp3", duration_seconds=60.0)
            for i in range(1, 4)
        ]
        image_paths = {f"seg_{i:03d}": tmp_path / f"seg_{i:03d}.png" for i in range(1, 4)}

        with patch("src.clients.remotion.get_settings", return_value=mock_settings):
            with patch("src.clients.remotion.httpx.Client") as mock_client:
                mock_response = MagicMock()
                mock_response.json.return_value = {"success": True}
                mock_response.raise_for_status = MagicMock()
                mock_post = mock_client.return_value.__enter__.return_value.post
                mock_post.return_value = mock_response

                client = RemotionClient()
                client.render_video(
                    job_id="job-005",
                    timeline=timeline,
                    audio_segments=audio_segments,
                    image_paths=image_paths,
                    storage=mock_storage,
                )

                # Verify the POST call
                mock_post.assert_called_once()
                call_args = mock_post.call_args

                # Check URL
                assert "render" in call_args[0][0]

                # Check request body
                request_body = call_args[1]["json"]
                assert request_body["job_id"] == "job-005"
                assert request_body["fps"] == 30
                assert request_body["width"] == 1920
                assert request_body["height"] == 1080
                assert len(request_body["segments"]) == 3


class TestGetRemotionClient:
    """Tests for get_remotion_client factory function."""

    def test_returns_remotion_client(self) -> None:
        """Test that factory returns RemotionClient instance."""
        mock_settings = MagicMock()
        mock_settings.remotion_service_url = "http://localhost:3000"

        with patch("src.clients.remotion.get_settings", return_value=mock_settings):
            client = get_remotion_client()

        assert isinstance(client, RemotionClient)

    def test_returns_singleton(self) -> None:
        """Test that factory returns the same instance."""
        mock_settings = MagicMock()
        mock_settings.remotion_service_url = "http://localhost:3000"

        # Reset singleton
        import src.clients.remotion
        src.clients.remotion._remotion_client = None

        with patch("src.clients.remotion.get_settings", return_value=mock_settings):
            client1 = get_remotion_client()
            client2 = get_remotion_client()

        assert client1 is client2
