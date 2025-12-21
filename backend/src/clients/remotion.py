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

    def health_check(self) -> bool:
        """Check if renderer is healthy."""
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self._base_url}/health")
                return response.status_code == 200
        except Exception as e:
            logger.warning(f"Remotion health check failed: {e}")
            return False

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
        segments_data = []
        audio_map = {seg.segment_id: seg for seg in audio_segments}

        for segment in timeline.segments:
            audio_seg = audio_map.get(segment.segment_id)
            image_path = image_paths.get(segment.segment_id)

            seg_data: dict[str, Any] = {
                "segment_id": segment.segment_id,
                "start_time_seconds": segment.start_time_seconds,
                "duration_seconds": segment.duration_seconds,
                "slide": {
                    "title": segment.slide.title,
                    "bullets": segment.slide.bullets,
                    "visual_prompt": segment.slide.visual_prompt,
                },
                "narration_text": segment.narration_text,
            }

            # Add asset paths (use file:// URLs for local paths)
            if audio_seg:
                seg_data["audio_path"] = f"file://{audio_seg.path.absolute()}"
            if image_path:
                seg_data["image_path"] = f"file://{image_path.absolute()}"

            segments_data.append(seg_data)

        output_path = storage.get_video_path(job_id)

        # Build render request
        render_request = {
            "job_id": job_id,
            "output_path": str(output_path.absolute()),
            "fps": 30,
            "width": 1920,
            "height": 1080,
            "title": timeline.title,
            "total_duration_seconds": timeline.total_duration_seconds,
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
