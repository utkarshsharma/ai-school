"""Gemini API client for content generation."""

import json
import logging
import os
import threading
from typing import Any

import google.generativeai as genai

from src.config import get_settings
from src.utils.retry import retry_call

logger = logging.getLogger(__name__)


class GeminiRateLimiter:
    """Thread-safe rate limiter for Gemini API calls.

    Limits concurrent API calls to avoid hitting rate limits,
    especially important when generating images in parallel.
    """

    def __init__(self, max_concurrent: int = 3):
        """Initialize the rate limiter.

        Args:
            max_concurrent: Maximum concurrent Gemini API calls.
                          Default is 3 to stay well under the 60 req/min limit.
        """
        self._semaphore = threading.Semaphore(max_concurrent)
        self._max = max_concurrent
        logger.info(f"Gemini rate limiter initialized: max {max_concurrent} concurrent calls")

    def __enter__(self):
        self._semaphore.acquire()
        return self

    def __exit__(self, *args):
        self._semaphore.release()


# Global rate limiter - controls concurrent Gemini calls across all threads
_rate_limiter: GeminiRateLimiter | None = None


def get_gemini_rate_limiter() -> GeminiRateLimiter:
    """Get the global Gemini rate limiter singleton."""
    global _rate_limiter
    if _rate_limiter is None:
        max_concurrent = int(os.getenv("GEMINI_MAX_CONCURRENT", "3"))
        _rate_limiter = GeminiRateLimiter(max_concurrent=max_concurrent)
    return _rate_limiter

# Model constants from INSTRUCTIONS.md
CONTENT_MODEL = "gemini-3-flash-preview"  # For timeline generation
IMAGE_MODEL = "gemini-2.5-flash-image"  # For slide image generation


class GeminiError(Exception):
    """Base exception for Gemini API errors."""

    pass


class GeminiRetryableError(GeminiError):
    """Retryable Gemini error (rate limit, transient failure, malformed response)."""

    pass


# Retry configuration for Gemini API calls
GEMINI_MAX_RETRIES = int(os.getenv("GEMINI_MAX_RETRIES", "3"))
GEMINI_RETRY_BASE_DELAY = float(os.getenv("GEMINI_RETRY_BASE_DELAY", "2.0"))


class GeminiClient:
    """Client for Gemini API interactions."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.gemini_api_key:
            raise GeminiError("GEMINI_API_KEY not configured")

        genai.configure(api_key=settings.gemini_api_key)
        self._content_model = genai.GenerativeModel(CONTENT_MODEL)

    def generate_timeline(
        self,
        pdf_content: str,
        filename: str,
        job_id: str,
    ) -> dict[str, Any]:
        """Generate video timeline from PDF content.

        Uses retry with exponential backoff for transient errors.

        Args:
            pdf_content: Extracted text from PDF
            filename: Original PDF filename
            job_id: Job ID for logging

        Returns:
            Parsed timeline JSON

        Raises:
            GeminiError: If generation or parsing fails after all retries
        """
        logger.info(f"[{job_id}] Generating timeline for: {filename}")

        prompt = self._build_timeline_prompt(pdf_content, filename)

        def _call_api() -> dict[str, Any]:
            """Inner function for API call with retry logic."""
            try:
                response = self._content_model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.7,
                        top_p=0.95,
                        max_output_tokens=8192,
                        response_mime_type="application/json",
                    ),
                )

                if not response.text:
                    # Empty response is retryable
                    raise GeminiRetryableError("Empty response from Gemini")

                # Parse JSON response
                try:
                    timeline_data = json.loads(response.text)
                except json.JSONDecodeError as e:
                    # JSON parse error is retryable (might be truncated response)
                    raise GeminiRetryableError(f"Invalid JSON response: {e}") from e

                logger.info(
                    f"[{job_id}] Generated timeline with "
                    f"{len(timeline_data.get('segments', []))} segments"
                )

                return timeline_data

            except GeminiRetryableError:
                raise
            except Exception as e:
                # Treat other API errors as retryable
                logger.warning(f"[{job_id}] Gemini API error (will retry): {e}")
                raise GeminiRetryableError(f"Gemini API error: {e}") from e

        try:
            return retry_call(
                _call_api,
                max_retries=GEMINI_MAX_RETRIES,
                base_delay=GEMINI_RETRY_BASE_DELAY,
                retryable_exceptions=(GeminiRetryableError,),
                context=job_id,
            )
        except GeminiRetryableError as e:
            # Convert to non-retryable error after all retries exhausted
            raise GeminiError(str(e)) from e

    def _build_timeline_prompt(self, pdf_content: str, filename: str) -> str:
        """Build the prompt for timeline generation."""
        return f"""You are an expert educational content designer creating teacher training videos.

TASK: Analyze this curriculum chapter and create a detailed video timeline for training teachers on how to teach this topic effectively.

SOURCE DOCUMENT: {filename}

CONTENT:
{pdf_content}

---

Create a teacher training video timeline following these requirements:

1. VIDEO STRUCTURE:
   - Total duration: 5-10 minutes (300-600 seconds)
   - 5-12 segments, each 30-90 seconds
   - Each segment focuses on ONE teaching concept or technique

2. SEGMENT CONTENT:
   - Title: Clear, actionable headline (e.g., "Introducing the Water Cycle")
   - Bullets: 2-4 key teaching points teachers should convey
   - Narration: Full script for teacher training (what the narrator will say)
   - Visual prompt: Description for generating a clean, educational slide background

3. PEDAGOGICAL FOCUS:
   - Explain HOW to teach concepts, not just WHAT the concepts are
   - Include age-appropriate teaching strategies
   - Suggest real-world examples and analogies
   - Address common student misconceptions
   - Include engagement techniques (questions, activities)

4. SLIDE VISUALS:
   - Clean, minimalist, pedagogy-focused
   - Educational diagrams, not decorative art
   - Professional, not cartoonish

OUTPUT FORMAT (strict JSON):
{{
  "version": "1.0",
  "title": "Teacher Training: [Topic Name]",
  "topic_summary": "Brief summary of what teachers will learn",
  "target_age_group": "Age range of students (e.g., '10-12 years')",
  "total_duration_seconds": [total duration],
  "segments": [
    {{
      "segment_id": "seg_001",
      "start_time_seconds": 0,
      "duration_seconds": [duration],
      "slide": {{
        "title": "Segment Title",
        "bullets": ["Point 1", "Point 2", "Point 3"],
        "visual_prompt": "Description for slide image generation"
      }},
      "narration_text": "Full narration script for this segment..."
    }},
    ...
  ]
}}

CRITICAL REQUIREMENTS:
- Segments must be sequential (seg_001, seg_002, etc.)
- start_time_seconds must equal the sum of previous segment durations
- No gaps or overlaps between segments
- All narration_text must be substantial (50-300 words per segment)
- All fields are required and must be non-empty

Generate the complete timeline JSON now:"""


# Singleton instance
_gemini_client: GeminiClient | None = None


def get_gemini_client() -> GeminiClient:
    """Get Gemini client singleton."""
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = GeminiClient()
    return _gemini_client
