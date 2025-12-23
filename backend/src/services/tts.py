"""Text-to-Speech service using Google Cloud TTS API.

Uses REST API with API key authentication for simplicity.
Includes retry logic for transient API failures.
"""

import base64
import io
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import httpx
from mutagen.mp3 import MP3

from src.config import get_settings
from src.schemas.timeline import Timeline
from src.services.storage import StorageService
from src.utils.retry import retry_call

logger = logging.getLogger(__name__)

# Number of parallel TTS generation workers (default: 4)
TTS_WORKERS = int(os.getenv("TTS_WORKERS", "4"))

# Retry configuration for TTS API calls
TTS_MAX_RETRIES = int(os.getenv("TTS_MAX_RETRIES", "3"))
TTS_RETRY_BASE_DELAY = float(os.getenv("TTS_RETRY_BASE_DELAY", "1.0"))

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


class TTSRetryableError(TTSError):
    """Retryable TTS error (timeout, network error, server error)."""

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
        """Generate audio for all segments in timeline in parallel.

        Uses ThreadPoolExecutor to generate multiple audio segments concurrently.
        Google TTS API has generous rate limits, so parallel generation is safe.

        Args:
            timeline: Validated timeline with narration text
            job_id: Job identifier

        Returns:
            List of generated audio segments (in timeline order)

        Raises:
            TTSError: If any audio generation fails
        """
        num_segments = len(timeline.segments)
        logger.info(f"[{job_id}] Generating audio for {num_segments} segments (parallel, {TTS_WORKERS} workers)")

        segment_results: dict[str, AudioSegment] = {}
        errors: list[str] = []

        # Use ThreadPoolExecutor for parallel audio generation
        with ThreadPoolExecutor(max_workers=TTS_WORKERS) as executor:
            # Submit all audio generation tasks
            futures = {
                executor.submit(
                    self._generate_segment_audio,
                    segment_id=segment.segment_id,
                    text=segment.narration_text,
                    target_duration=segment.duration_seconds,
                    job_id=job_id,
                ): segment.segment_id
                for segment in timeline.segments
            }

            # Collect results as they complete
            for future in as_completed(futures):
                segment_id = futures[future]
                try:
                    audio_segment = future.result()
                    segment_results[segment_id] = audio_segment
                    logger.info(f"[{job_id}] Audio ready: {segment_id} ({len(segment_results)}/{num_segments})")
                except Exception as e:
                    error_msg = f"Audio generation failed for {segment_id}: {e}"
                    logger.error(f"[{job_id}] {error_msg}")
                    errors.append(error_msg)

        # If any errors occurred, raise with all error messages
        if errors:
            raise TTSError("; ".join(errors))

        # Maintain timeline order (important for video rendering)
        audio_segments = [segment_results[seg.segment_id] for seg in timeline.segments]

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

        Uses retry logic for transient API failures.

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

        def _call_tts_api() -> dict:
            """Inner function for TTS API call with retry."""
            try:
                with httpx.Client(timeout=60.0) as client:
                    response = client.post(
                        TTS_API_URL,
                        params={"key": self._api_key},
                        json=request_body,
                    )
                    response.raise_for_status()
                    return response.json()
            except httpx.TimeoutException as e:
                # Timeout is retryable
                raise TTSRetryableError(f"TTS request timed out for {segment_id}") from e
            except httpx.HTTPStatusError as e:
                # 5xx errors are retryable, 4xx are not
                if e.response.status_code >= 500:
                    raise TTSRetryableError(
                        f"TTS API error {e.response.status_code}: {e.response.text}"
                    ) from e
                # 4xx errors are not retryable
                raise TTSError(
                    f"TTS API error: {e.response.status_code} - {e.response.text}"
                ) from e
            except httpx.RequestError as e:
                # Network errors are retryable
                raise TTSRetryableError(f"TTS network error: {e}") from e

        # Call TTS API with retry
        try:
            result = retry_call(
                _call_tts_api,
                max_retries=TTS_MAX_RETRIES,
                base_delay=TTS_RETRY_BASE_DELAY,
                retryable_exceptions=(TTSRetryableError,),
                context=f"{job_id}/{segment_id}",
            )
        except TTSRetryableError as e:
            # Convert to non-retryable error after all retries exhausted
            raise TTSError(str(e)) from e

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
