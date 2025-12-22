"""Remotion renderer client."""

import logging
from pathlib import Path
from typing import Any

import httpx

from src.config import get_settings
from src.schemas.timeline import Timeline
from src.services.storage import StorageService
from src.services.tts import AudioSegment

logger = logging.getLogger(__name__)


class RemotionError(Exception):
    """Error communicating with Remotion renderer."""

    pass


class RemotionClient:
    """Client for the Remotion rendering service."""

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.remotion_service_url
        self._timeout = httpx.Timeout(600.0)  # 10 minutes for rendering
        self._backend_url = "http://localhost:8000"  # Backend URL for serving assets
        self._storage_base = settings.storage_base_path

    def health_check(self) -> bool:
        """Check if renderer is healthy."""
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self._base_url}/health")
                return response.status_code == 200
        except Exception as e:
            logger.warning(f"Remotion health check failed: {e}")
            return False

    def _path_to_url(self, file_path: Path) -> str:
        """Convert a storage file path to an HTTP URL.

        Remotion can't use file:// URLs, so we serve files via the backend.
        """
        # Get relative path from storage base
        try:
            relative_path = file_path.relative_to(self._storage_base)
        except ValueError:
            # If not relative to storage base, use the absolute path
            relative_path = file_path

        return f"{self._backend_url}/storage/{relative_path}"

    def render_video(
        self,
        job_id: str,
        timeline: Timeline,
        audio_segments: list[AudioSegment],
        image_paths: dict[str, Path],
        storage: StorageService,
    ) -> Path:
        """Render video from timeline and assets.

        Args:
            job_id: Job identifier
            timeline: Validated timeline
            audio_segments: Generated audio segments
            image_paths: Mapping of segment_id to image paths
            storage: Storage service for output path

        Returns:
            Path to rendered video

        Raises:
            RemotionError: If rendering fails
        """
        logger.info(f"[{job_id}] Requesting video render")

        # Build segment data with asset paths
        # Use actual audio duration for slide timing (not Gemini's estimate)
        segments_data = []
        audio_map = {seg.segment_id: seg for seg in audio_segments}

        # Small buffer after audio ends before transitioning (seconds)
        transition_buffer = 0.5

        for segment in timeline.segments:
            audio_seg = audio_map.get(segment.segment_id)
            image_path = image_paths.get(segment.segment_id)

            # Use actual audio duration + buffer, fall back to timeline if no audio
            if audio_seg and audio_seg.duration_seconds > 0:
                actual_duration = audio_seg.duration_seconds + transition_buffer
            else:
                actual_duration = segment.duration_seconds

            seg_data: dict[str, Any] = {
                "segment_id": segment.segment_id,
                "start_time_seconds": segment.start_time_seconds,
                "duration_seconds": actual_duration,
                "slide": {
                    "title": segment.slide.title,
                    "bullets": segment.slide.bullets,
                    "visual_prompt": segment.slide.visual_prompt,
                },
                "narration_text": segment.narration_text,
            }

            # Add asset paths (use HTTP URLs so Remotion can download them)
            if audio_seg:
                seg_data["audio_path"] = self._path_to_url(audio_seg.path)
            if image_path:
                seg_data["image_path"] = self._path_to_url(image_path)

            segments_data.append(seg_data)

            logger.debug(
                f"[{job_id}] {segment.segment_id}: "
                f"audio={audio_seg.duration_seconds:.1f}s, "
                f"timeline={segment.duration_seconds:.1f}s, "
                f"using={actual_duration:.1f}s"
                if audio_seg else f"[{job_id}] {segment.segment_id}: no audio, using timeline {segment.duration_seconds:.1f}s"
            )

        # Calculate actual total duration from segments
        actual_total_duration = sum(seg["duration_seconds"] for seg in segments_data)
        logger.info(
            f"[{job_id}] Duration: {actual_total_duration:.1f}s actual vs {timeline.total_duration_seconds:.1f}s timeline"
        )

        output_path = storage.get_video_path(job_id)

        # Build render request
        render_request = {
            "job_id": job_id,
            "output_path": str(output_path.absolute()),
            "fps": 30,
            "width": 1920,
            "height": 1080,
            "title": timeline.title,
            "total_duration_seconds": actual_total_duration,
            "segments": segments_data,
        }

        logger.info(f"[{job_id}] Sending render request for {len(segments_data)} segments")

        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    f"{self._base_url}/render",
                    json=render_request,
                )
                response.raise_for_status()
                result = response.json()
        except httpx.TimeoutException:
            raise RemotionError("Render request timed out")
        except httpx.HTTPStatusError as e:
            raise RemotionError(f"Render failed: {e.response.text}")
        except Exception as e:
            raise RemotionError(f"Render request failed: {e}")

        if not result.get("success"):
            raise RemotionError(f"Render failed: {result.get('error', 'Unknown error')}")

        logger.info(f"[{job_id}] Render complete: {output_path}")
        return output_path


# Singleton
_remotion_client: RemotionClient | None = None


def get_remotion_client() -> RemotionClient:
    """Get Remotion client singleton."""
    global _remotion_client
    if _remotion_client is None:
        _remotion_client = RemotionClient()
    return _remotion_client
