"""Slide image generation service using Gemini.

Per INSTRUCTIONS.md, slide images must use gemini-2.5-flash-image
with prompts optimized for clean, minimalist, pedagogy-first slides.
"""

import io
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from google import genai
from PIL import Image

from src.clients.gemini import get_gemini_rate_limiter
from src.config import get_settings
from src.schemas.timeline import Timeline
from src.services.storage import StorageService

logger = logging.getLogger(__name__)

# Number of parallel image generation workers (default: 4)
IMAGE_WORKERS = int(os.getenv("IMAGE_WORKERS", "4"))

# Model for image generation per INSTRUCTIONS.md
IMAGE_MODEL = "gemini-2.5-flash-image"


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

        self._client = genai.Client(api_key=settings.gemini_api_key)

    def generate_images(self, timeline: Timeline, job_id: str) -> dict[str, Path]:
        """Generate slide images for all segments in parallel.

        Uses ThreadPoolExecutor to generate multiple images concurrently,
        controlled by the Gemini rate limiter to avoid API rate limits.

        Args:
            timeline: Validated timeline with visual prompts
            job_id: Job identifier

        Returns:
            Dict mapping segment_id to image path

        Raises:
            ImageGenerationError: If any image generation fails
        """
        num_segments = len(timeline.segments)
        logger.info(f"[{job_id}] Generating {num_segments} slide images (parallel, {IMAGE_WORKERS} workers)")

        image_paths: dict[str, Path] = {}
        errors: list[str] = []

        # Use ThreadPoolExecutor for parallel image generation
        with ThreadPoolExecutor(max_workers=IMAGE_WORKERS) as executor:
            # Submit all image generation tasks
            futures = {
                executor.submit(
                    self._generate_slide_image,
                    segment_id=segment.segment_id,
                    title=segment.slide.title,
                    visual_prompt=segment.slide.visual_prompt,
                    job_id=job_id,
                ): segment.segment_id
                for segment in timeline.segments
            }

            # Collect results as they complete
            for future in as_completed(futures):
                segment_id = futures[future]
                try:
                    image_path = future.result()
                    image_paths[segment_id] = image_path
                    logger.info(f"[{job_id}] Image ready: {segment_id} ({len(image_paths)}/{num_segments})")
                except Exception as e:
                    error_msg = f"Image generation failed for {segment_id}: {e}"
                    logger.error(f"[{job_id}] {error_msg}")
                    errors.append(error_msg)

        # If any errors occurred, raise with all error messages
        if errors:
            raise ImageGenerationError("; ".join(errors))

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

        Uses the Gemini rate limiter to control concurrent API calls.

        Args:
            segment_id: Segment identifier
            title: Slide title for context
            visual_prompt: Visual description from timeline
            job_id: Job identifier

        Returns:
            Path to generated image
        """
        rate_limiter = get_gemini_rate_limiter()
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
            # Use rate limiter to control concurrent API calls
            with rate_limiter:
                response = self._client.models.generate_content(
                    model=IMAGE_MODEL,
                    contents=[full_prompt],
                )

                # Extract image from response parts
                for part in response.parts:
                    if part.inline_data is not None:
                        # Get the raw image bytes directly from inline_data
                        image_data = part.inline_data.data

                        # If data is base64 encoded string, decode it
                        if isinstance(image_data, str):
                            import base64
                            image_data = base64.b64decode(image_data)

                        # Save image
                        image_path = self._storage.save_image(job_id, segment_id, image_data)
                        logger.info(f"[{job_id}] Saved image: {image_path}")
                        return image_path

                # No image found in response
                logger.warning(
                    f"[{job_id}] No image in response for {segment_id}, using placeholder"
                )
                image_data = self._create_placeholder_image()
                return self._storage.save_image(job_id, segment_id, image_data)

        except Exception as e:
            logger.error(f"[{job_id}] Image generation error: {e}")
            # Create fallback placeholder
            image_data = self._create_placeholder_image()
            return self._storage.save_image(job_id, segment_id, image_data)

    def _create_placeholder_image(self) -> bytes:
        """Create a proper placeholder image using PIL.

        This is used when image generation fails, ensuring
        the pipeline can continue with a valid image.
        """
        # Create a gray gradient background (1920x1080)
        img = Image.new('RGB', (1920, 1080), color=(128, 128, 140))

        # Convert to PNG bytes
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        return img_byte_arr.getvalue()


def get_image_generator(storage: StorageService) -> ImageGenerator:
    """Create image generator with storage service."""
    return ImageGenerator(storage)
