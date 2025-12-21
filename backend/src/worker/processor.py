"""Background job processor for video generation pipeline.

This module orchestrates the complete pipeline:
1. PDF extraction
2. Content generation (Gemini) + eval
3. Image generation (Gemini)
4. TTS audio generation
5. Video rendering (Remotion)

Per INSTRUCTIONS.md: The system is asynchronous - video generation
runs as a background job, the API immediately returns a job ID.
"""

import logging
import threading
from datetime import datetime
from pathlib import Path
from queue import Queue
from typing import Callable

from sqlalchemy.orm import Session

from src.models.database import get_session_local
from src.models.job import Job, JobStatus, JobStage
from src.services.storage import get_storage_service, StorageService
from src.services.pdf_extractor import get_pdf_extractor
from src.services.content_generator import get_content_generator, ContentGenerationError
from src.services.image_generator import get_image_generator, ImageGenerationError
from src.services.tts import get_tts_service, TTSError
from src.clients.remotion import get_remotion_client, RemotionError

logger = logging.getLogger(__name__)

# Simple in-memory job queue for MVP
# Will be replaced with proper queue (Redis/RabbitMQ) in V1
_job_queue: Queue[str] = Queue()
_worker_thread: threading.Thread | None = None


def enqueue_job(job_id: str) -> None:
    """Add a job to the processing queue.

    Args:
        job_id: Job ID to process
    """
    logger.info(f"Enqueueing job: {job_id}")
    _job_queue.put(job_id)


def start_worker() -> None:
    """Start the background worker thread."""
    global _worker_thread
    if _worker_thread is None or not _worker_thread.is_alive():
        _worker_thread = threading.Thread(target=_worker_loop, daemon=True)
        _worker_thread.start()
        logger.info("Background worker started")


def _worker_loop() -> None:
    """Main worker loop - processes jobs from queue."""
    while True:
        try:
            job_id = _job_queue.get()
            logger.info(f"Processing job: {job_id}")
            _process_job(job_id)
        except Exception as e:
            logger.error(f"Worker error: {e}", exc_info=True)


def _process_job(job_id: str) -> None:
    """Process a single job through the pipeline.

    Args:
        job_id: Job ID to process
    """
    SessionLocal = get_session_local()
    db = SessionLocal()

    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            logger.error(f"Job not found: {job_id}")
            return

        if job.status != JobStatus.PENDING:
            logger.warning(f"Job {job_id} is not pending, skipping")
            return

        storage = get_storage_service()
        _run_pipeline(job, db, storage)

    except Exception as e:
        logger.error(f"[{job_id}] Pipeline failed: {e}", exc_info=True)
        # Update job status in fresh session
        try:
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job.mark_failed(str(e))
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


def _run_pipeline(job: Job, db: Session, storage: StorageService) -> None:
    """Run the complete video generation pipeline.

    Args:
        job: Job model
        db: Database session
        storage: Storage service
    """
    job_id = job.id
    logger.info(f"[{job_id}] Starting pipeline")

    # Stage 1: PDF Extraction
    _update_stage(job, db, JobStage.EXTRACT, 0)
    logger.info(f"[{job_id}] Stage 1: PDF extraction")

    pdf_extractor = get_pdf_extractor()
    pdf_content = pdf_extractor.extract(Path(job.pdf_path))
    _update_stage(job, db, JobStage.EXTRACT, 100)

    # Stage 2: Content Generation
    _update_stage(job, db, JobStage.GENERATE, 0)
    logger.info(f"[{job_id}] Stage 2: Content generation")

    try:
        content_generator = get_content_generator(storage)
        timeline = content_generator.generate_timeline(pdf_content, job_id)
        job.timeline_path = str(storage.get_timeline_path(job_id))
        job.slide_count = len(timeline.segments)
        db.commit()
    except ContentGenerationError as e:
        job.mark_failed(str(e), JobStage.GENERATE)
        db.commit()
        raise

    _update_stage(job, db, JobStage.GENERATE, 100)

    # Stage 3: Image Generation
    _update_stage(job, db, JobStage.IMAGES, 0)
    logger.info(f"[{job_id}] Stage 3: Image generation")

    try:
        image_generator = get_image_generator(storage)
        image_paths = image_generator.generate_images(timeline, job_id)
    except ImageGenerationError as e:
        job.mark_failed(str(e), JobStage.IMAGES)
        db.commit()
        raise

    _update_stage(job, db, JobStage.IMAGES, 100)

    # Stage 4: TTS Generation
    _update_stage(job, db, JobStage.TTS, 0)
    logger.info(f"[{job_id}] Stage 4: TTS generation")

    try:
        tts_service = get_tts_service(storage)
        audio_segments = tts_service.generate_audio(timeline, job_id)
    except TTSError as e:
        job.mark_failed(str(e), JobStage.TTS)
        db.commit()
        raise

    _update_stage(job, db, JobStage.TTS, 100)

    # Stage 5: Video Rendering
    _update_stage(job, db, JobStage.RENDER, 0)
    logger.info(f"[{job_id}] Stage 5: Video rendering")

    try:
        remotion_client = get_remotion_client()
        video_path = remotion_client.render_video(
            job_id=job_id,
            timeline=timeline,
            audio_segments=audio_segments,
            image_paths=image_paths,
            storage=storage,
        )
        job.video_path = str(video_path)
        job.video_duration_seconds = timeline.total_duration_seconds
    except RemotionError as e:
        job.mark_failed(str(e), JobStage.RENDER)
        db.commit()
        raise

    # Mark complete
    job.mark_completed()
    db.commit()

    logger.info(f"[{job_id}] Pipeline completed successfully")


def _update_stage(job: Job, db: Session, stage: JobStage, progress: int) -> None:
    """Update job stage and progress."""
    job.status = JobStatus.PROCESSING
    job.current_stage = stage
    job.stage_progress = progress
    job.updated_at = datetime.utcnow()
    db.commit()
