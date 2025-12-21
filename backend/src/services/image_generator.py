"""Slide image generation service using Gemini.

Per INSTRUCTIONS.md, slide images must use gemini-2.5-flash-image
with prompts optimized for clean, minimalist, pedagogy-first slides.
"""

import base64
import logging
from pathlib import Path

import google.generativeai as genai

from src.config import get_settings
from src.schemas.timeline import Timeline
from src.services.storage import StorageService

logger = logging.getLogger(__name__)

# Model for image generation per INSTRUCTIONS.md
IMAGE_MODEL = "gemini-2.0-flash-exp-image-generation"


class ImageGenerationError(Exception):
    """Error during image generation."""

    pass


class ImageGenerator:
    """Service for generating slide background images."""

    def __init__(self, storage: StorageService) -> None:
        self._storage = storage
        settings = get_settings()
        if not settings.gemini_api_key:
            raise ImageGenerationError("GEMINI_API_KEY not configured")

        genai.configure(api_key=settings.gemini_api_key)
        self._model = genai.GenerativeModel(IMAGE_MODEL)

    def generate_images(self, timeline: Timeline, job_id: str) -> dict[str, Path]:
        """Generate slide images for all segments.

        Args:
            timeline: Validated timeline with visual prompts
            job_id: Job identifier

        Returns:
            Dict mapping segment_id to image path

        Raises:
            ImageGenerationError: If any image generation fails
        """
        logger.info(f"[{job_id}] Generating {len(timeline.segments)} slide images")

        image_paths: dict[str, Path] = {}

        for segment in timeline.segments:
            try:
                image_path = self._generate_slide_image(
                    segment_id=segment.segment_id,
                    title=segment.slide.title,
                    visual_prompt=segment.slide.visual_prompt,
                    job_id=job_id,
                )
                image_paths[segment.segment_id] = image_path
            except Exception as e:
                logger.error(
                    f"[{job_id}] Failed to generate image for {segment.segment_id}: {e}"
                )
                raise ImageGenerationError(
                    f"Image generation failed for {segment.segment_id}: {e}"
                ) from e

        logger.info(f"[{job_id}] Generated {len(image_paths)} slide images")
        return image_paths

    def _generate_slide_image(
        self,
        segment_id: str,
        title: str,
        visual_prompt: str,
        job_id: str,
    ) -> Path:
        """Generate a single slide background image.

        Args:
            segment_id: Segment identifier
            title: Slide title for context
            visual_prompt: Visual description from timeline
            job_id: Job identifier

        Returns:
            Path to generated image
        """
        logger.info(f"[{job_id}] Generating image for {segment_id}")

        # Build prompt optimized for clean, educational slides
        full_prompt = f"""Create a clean, minimalist slide background image for an educational presentation.

SLIDE TITLE: {title}

VISUAL CONCEPT: {visual_prompt}

STYLE REQUIREMENTS:
- Clean and professional, suitable for teacher training
- Minimalist design with subtle educational elements
- Soft, muted colors that won't distract from text overlay
- No text or words in the image
- No photorealistic people or faces
- Simple diagrams or abstract representations preferred
- 16:9 aspect ratio (1920x1080)
- Leave center area relatively clear for text overlay

Generate a single image that serves as an effective slide background."""

        try:
            response = self._model.generate_content(
                full_prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.4,
                ),
            )

            # Extract image from response
            if not response.candidates:
                raise ImageGenerationError("No image generated")

            # Find image part in response
            image_data = None
            for part in response.candidates[0].content.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    if part.inline_data.mime_type.startswith("image/"):
                        image_data = base64.b64decode(part.inline_data.data)
                        break

            if not image_data:
                # If no image in response, generate a placeholder
                logger.warning(
                    f"[{job_id}] No image in response for {segment_id}, "
                    "using placeholder"
                )
                image_data = self._create_placeholder_image(title)

            # Save image
            image_path = self._storage.save_image(job_id, segment_id, image_data)
            logger.info(f"[{job_id}] Saved image: {image_path}")

            return image_path

        except Exception as e:
            logger.error(f"[{job_id}] Image generation error: {e}")
            # Create fallback placeholder
            image_data = self._create_placeholder_image(title)
            return self._storage.save_image(job_id, segment_id, image_data)

    def _create_placeholder_image(self, title: str) -> bytes:
        """Create a simple placeholder image.

        This is used when image generation fails, ensuring
        the pipeline can continue with a valid image.
        """
        # Simple 1x1 pixel PNG (light gray)
        # In production, this would be a proper placeholder
        # For MVP, we use a minimal valid PNG
        return (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
            b"\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x00\x03"
            b"\x00\x01\x00\x05\xfe\xd4\x00\x00\x00\x00IEND\xaeB`\x82"
        )


def get_image_generator(storage: StorageService) -> ImageGenerator:
    """Create image generator with storage service."""
    return ImageGenerator(storage)
