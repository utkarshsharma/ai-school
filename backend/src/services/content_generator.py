"""Content generation service using Gemini.

This service orchestrates:
1. Calling Gemini API for timeline generation
2. Running mandatory eval layer on output
3. Persisting validated timeline
"""

import json
import logging

from src.clients.gemini import get_gemini_client, GeminiError
from src.evals.timeline_eval import evaluate_timeline, TimelineEvalError
from src.schemas.timeline import Timeline
from src.services.pdf_extractor import PDFContent
from src.services.storage import StorageService

logger = logging.getLogger(__name__)


class ContentGenerationError(Exception):
    """Error during content generation."""

    pass


class ContentGenerator:
    """Service for generating video content from PDF."""

    def __init__(self, storage: StorageService) -> None:
        self._storage = storage
        self._gemini = get_gemini_client()

    def generate_timeline(
        self,
        pdf_content: PDFContent,
        job_id: str,
    ) -> Timeline:
        """Generate and validate timeline from PDF content.

        This method:
        1. Calls Gemini to generate timeline JSON
        2. Runs eval layer (MANDATORY - must pass before proceeding)
        3. Persists validated timeline
        4. Returns Timeline object

        Args:
            pdf_content: Extracted PDF content
            job_id: Job identifier for logging and storage

        Returns:
            Validated Timeline object

        Raises:
            ContentGenerationError: If generation or validation fails
        """
        logger.info(f"[{job_id}] Starting content generation")

        # Step 1: Generate timeline with Gemini
        try:
            raw_timeline = self._gemini.generate_timeline(
                pdf_content=pdf_content.text,
                filename=pdf_content.filename,
                job_id=job_id,
            )
        except GeminiError as e:
            raise ContentGenerationError(f"Gemini generation failed: {e}") from e

        # Step 2: Run mandatory eval layer
        # If this fails, job must fail - no auto-adjustment allowed
        try:
            timeline = evaluate_timeline(raw_timeline, job_id)
        except TimelineEvalError as e:
            raise ContentGenerationError(
                f"Timeline validation failed - job must be regenerated: {e}"
            ) from e

        # Step 3: Persist validated timeline
        timeline_json = json.dumps(raw_timeline, indent=2)
        timeline_path = self._storage.save_timeline(job_id, timeline_json)
        logger.info(f"[{job_id}] Timeline saved to: {timeline_path}")

        return timeline


def get_content_generator(storage: StorageService) -> ContentGenerator:
    """Create content generator with storage service."""
    return ContentGenerator(storage)
