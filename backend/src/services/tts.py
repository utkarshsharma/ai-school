"""Text-to-Speech service using Google Cloud TTS API.

Uses REST API with API key authentication for simplicity.
"""

import base64
import io
import logging
from dataclasses import dataclass
from pathlib import Path

import httpx
from mutagen.mp3 import MP3

from src.config import get_settings
from src.schemas.timeline import Timeline
from src.services.storage import StorageService

logger = logging.getLogger(__name__)

TTS_API_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"

# Voice configuration for teacher training narration
DEFAULT_VOICE = {
    "languageCode": "en-US",
    "name": "en-US-Journey-F",  # Natural, professional female voice
    "ssmlGender": "FEMALE",
}

DEFAULT_AUDIO_CONFIG = {
    "audioEncoding": "MP3",
    "speakingRate": 0.95,  # Slightly slower for clarity
    "pitch": 0,
    "volumeGainDb": 0,
}


class TTSError(Exception):
    """Error during text-to-speech generation."""

    pass


@dataclass
class AudioSegment:
    """Generated audio segment."""

    segment_id: str
    path: Path
    duration_seconds: float


class TTSService:
    """Service for generating narration audio."""

    def __init__(self, storage: StorageService) -> None:
        self._storage = storage
        settings = get_settings()
        if not settings.google_tts_api_key:
            raise TTSError("GOOGLE_TTS_API_KEY not configured")
        self._api_key = settings.google_tts_api_key

    def generate_audio(
        self,
        timeline: Timeline,
        job_id: str,
    ) -> list[AudioSegment]:
        """Generate audio for all segments in timeline.

        Args:
            timeline: Validated timeline with narration text
            job_id: Job identifier

        Returns:
            List of generated audio segments

        Raises:
            TTSError: If any audio generation fails
        """
        logger.info(f"[{job_id}] Generating audio for {len(timeline.segments)} segments")

        audio_segments: list[AudioSegment] = []

        for segment in timeline.segments:
            try:
                audio_segment = self._generate_segment_audio(
                    segment_id=segment.segment_id,
                    text=segment.narration_text,
                    target_duration=segment.duration_seconds,
                    job_id=job_id,
                )
                audio_segments.append(audio_segment)
            except Exception as e:
                logger.error(
                    f"[{job_id}] Failed to generate audio for {segment.segment_id}: {e}"
                )
                raise TTSError(
                    f"Audio generation failed for {segment.segment_id}: {e}"
                ) from e

        logger.info(f"[{job_id}] Generated {len(audio_segments)} audio segments")
        return audio_segments

    def _generate_segment_audio(
        self,
        segment_id: str,
        text: str,
        target_duration: float,
        job_id: str,
    ) -> AudioSegment:
        """Generate audio for a single segment.

        Args:
            segment_id: Segment identifier
            text: Narration text
            target_duration: Target duration in seconds (from timeline)
            job_id: Job identifier

        Returns:
            Generated audio segment
        """
        logger.info(f"[{job_id}] Generating audio for {segment_id}")

        # Build request
        request_body = {
            "input": {"text": text},
            "voice": DEFAULT_VOICE,
            "audioConfig": DEFAULT_AUDIO_CONFIG,
        }

        # Call TTS API
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    TTS_API_URL,
                    params={"key": self._api_key},
                    json=request_body,
                )
                response.raise_for_status()
                result = response.json()
        except httpx.TimeoutException:
            raise TTSError(f"TTS request timed out for {segment_id}")
        except httpx.HTTPStatusError as e:
            raise TTSError(f"TTS API error: {e.response.status_code} - {e.response.text}")

        # Extract audio content
        audio_content = result.get("audioContent")
        if not audio_content:
            raise TTSError(f"No audio content in response for {segment_id}")

        # Decode and save
        audio_bytes = base64.b64decode(audio_content)
        audio_path = self._storage.save_audio(job_id, segment_id, audio_bytes)

        # Get accurate duration using mutagen
        audio_duration = self._get_mp3_duration(audio_bytes)

        logger.info(
            f"[{job_id}] Audio for {segment_id}: {len(audio_bytes)} bytes, "
            f"{audio_duration:.1f}s (target: {target_duration:.1f}s)"
        )

        return AudioSegment(
            segment_id=segment_id,
            path=audio_path,
            duration_seconds=audio_duration,
        )

    def _get_mp3_duration(self, audio_bytes: bytes) -> float:
        """Get accurate MP3 duration using mutagen.

        Args:
            audio_bytes: Raw MP3 audio data

        Returns:
            Duration in seconds
        """
        try:
            audio_file = io.BytesIO(audio_bytes)
            mp3 = MP3(audio_file)
            return mp3.info.length
        except Exception as e:
            logger.warning(f"Failed to parse MP3 duration: {e}, using estimate")
            # Fallback to rough estimate (128kbps)
            return len(audio_bytes) / (128 * 1000 / 8)


def get_tts_service(storage: StorageService) -> TTSService:
    """Create TTS service with storage."""
    return TTSService(storage)
