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

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from queue import Queue

from mutagen.mp3 import MP3
from sqlalchemy.orm import Session

from src.models.database import get_session_local
from src.models.job import Job, JobStatus, JobStage
from src.schemas.timeline import Timeline
from src.services.storage import get_storage_service, StorageService
from src.services.pdf_extractor import get_pdf_extractor
from src.services.content_generator import get_content_generator, ContentGenerationError
from src.services.image_generator import get_image_generator, ImageGenerationError
from src.services.tts import get_tts_service, TTSError, AudioSegment
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


def resume_job_from_stage(job_id: str, from_stage: str) -> None:
    """Resume a job from a specific stage using existing artifacts.

    This allows resuming failed jobs without re-running expensive stages.

    Args:
        job_id: Job ID to resume
        from_stage: Stage to resume from ('images', 'tts', or 'render')
    """
    logger.info(f"[{job_id}] Resuming from stage: {from_stage}")

    SessionLocal = get_session_local()
    db = SessionLocal()

    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            logger.error(f"Job not found: {job_id}")
            return

        storage = get_storage_service()

        # Load timeline from storage (required for all resume stages)
        timeline_json = storage.load_timeline_json(job_id)
        if not timeline_json:
            raise ValueError(f"No timeline found for job {job_id}")

        timeline = Timeline.model_validate(json.loads(timeline_json))
        logger.info(f"[{job_id}] Loaded timeline: {len(timeline.segments)} segments")

        # Load existing images
        image_paths = storage.list_images(job_id)
        logger.info(f"[{job_id}] Found {len(image_paths)} existing images")

        # Load existing audio and convert to AudioSegment objects with actual durations
        audio_paths = storage.list_audio(job_id)
        audio_segments = []
        for seg_id, path in audio_paths.items():
            duration = _get_audio_duration(path)
            audio_segments.append(AudioSegment(segment_id=seg_id, path=path, duration_seconds=duration))
        logger.info(f"[{job_id}] Found {len(audio_segments)} existing audio files")

        # Resume from specified stage
        if from_stage == "images":
            # Re-run from images onwards
            _update_stage(job, db, JobStage.IMAGES, 0)
            try:
                image_generator = get_image_generator(storage)
                image_paths = image_generator.generate_images(timeline, job_id)
            except ImageGenerationError as e:
                job.mark_failed(str(e), JobStage.IMAGES)
                db.commit()
                raise
            _update_stage(job, db, JobStage.IMAGES, 100)
            from_stage = "tts"  # Continue to next stage

        if from_stage == "tts":
            # Re-run TTS and render
            _update_stage(job, db, JobStage.TTS, 0)
            try:
                tts_service = get_tts_service(storage)
                audio_segments = tts_service.generate_audio(timeline, job_id)
            except TTSError as e:
                job.mark_failed(str(e), JobStage.TTS)
                db.commit()
                raise
            _update_stage(job, db, JobStage.TTS, 100)
            from_stage = "render"  # Continue to next stage

        if from_stage == "render":
            # Just re-run render using existing artifacts
            _update_stage(job, db, JobStage.RENDER, 0)
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
        logger.info(f"[{job_id}] Resume completed successfully")

    except Exception as e:
        logger.error(f"[{job_id}] Resume failed: {e}", exc_info=True)
        try:
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job.mark_failed(str(e))
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


def _get_audio_duration(path: Path) -> float:
    """Get audio file duration using mutagen.

    Args:
        path: Path to MP3 file

    Returns:
        Duration in seconds, or 0 if parsing fails
    """
    try:
        mp3 = MP3(path)
        return mp3.info.length
    except Exception as e:
        logger.warning(f"Failed to get audio duration for {path}: {e}")
        return 0


def enqueue_resume(job_id: str, from_stage: str) -> None:
    """Enqueue a job resume request.

    Args:
        job_id: Job ID to resume
        from_stage: Stage to resume from
    """
    # For now, run directly in a new thread (simpler than extending queue)
    thread = threading.Thread(
        target=resume_job_from_stage,
        args=(job_id, from_stage),
        daemon=True,
    )
    thread.start()
    logger.info(f"Started resume thread for job {job_id} from stage {from_stage}")
