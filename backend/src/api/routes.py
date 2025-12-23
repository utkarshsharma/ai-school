"""API routes for job management."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from src.models.database import get_db
from src.models.job import Job, JobStatus
from src.schemas.job import JobResponse, JobListResponse
from src.services.storage import get_storage_service
from src.worker.processor import enqueue_job, enqueue_resume

# API version - increment for breaking changes
API_VERSION = "1.0.0"

router = APIRouter(prefix="/api", tags=["jobs"])


@router.get("/version")
async def get_version() -> dict:
    """Get API version information."""
    return {
        "api_version": API_VERSION,
        "schema_version": "1.0",
        "service": "ai-school-backend",
    }


@router.post("/jobs", response_model=JobResponse, status_code=201)
async def create_job(
    file: Annotated[UploadFile, File(description="PDF file to process")],
    db: Annotated[Session, Depends(get_db)],
) -> JobResponse:
    """Upload a PDF and create a new video generation job.

    Returns immediately with job ID. Poll /api/jobs/{job_id} for status.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    # Read file content
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    if len(content) > 50 * 1024 * 1024:  # 50MB limit
        raise HTTPException(status_code=400, detail="File too large (max 50MB)")

    # Save PDF
    storage = get_storage_service()
    job = Job(original_filename=file.filename, pdf_path="")

    # Save to get job ID
    db.add(job)
    db.flush()

    # Now save PDF with job ID
    pdf_path = storage.save_pdf(job.id, content, file.filename)
    job.pdf_path = str(pdf_path)
    db.commit()

    # Enqueue for processing
    enqueue_job(job.id)

    return JobResponse.model_validate(job)


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    db: Annotated[Session, Depends(get_db)],
    page: int = 1,
    page_size: int = 20,
) -> JobListResponse:
    """List all jobs with pagination."""
    offset = (page - 1) * page_size
    jobs = db.query(Job).order_by(Job.created_at.desc()).offset(offset).limit(page_size).all()
    total = db.query(Job).count()

    return JobListResponse(
        jobs=[JobResponse.model_validate(j) for j in jobs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> JobResponse:
    """Get job status and details."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobResponse.model_validate(job)


@router.delete("/jobs/{job_id}", status_code=204)
async def delete_job(
    job_id: str,
    db: Annotated[Session, Depends(get_db)],
    hard_delete: bool = False,
) -> None:
    """Delete a job.

    Args:
        job_id: Job ID to delete
        hard_delete: If True, also delete all artifacts (images, audio, etc).
                     If False (default), only delete from database, keeping artifacts.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Only delete artifacts if hard_delete is requested
    if hard_delete:
        storage = get_storage_service()
        storage.delete_job_artifacts(job_id)

    # Delete from database
    db.delete(job)
    db.commit()


@router.get("/jobs/{job_id}/video")
async def download_video(
    job_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> FileResponse:
    """Download the generated video."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Video not ready. Job status: {job.status.value}",
        )

    if not job.video_path:
        raise HTTPException(status_code=404, detail="Video file not found")

    video_path = Path(job.video_path)
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video file missing")

    return FileResponse(
        path=video_path,
        media_type="video/mp4",
        filename=f"{job.original_filename.replace('.pdf', '')}_training.mp4",
    )


@router.post("/jobs/{job_id}/retry", response_model=JobResponse)
async def retry_job(
    job_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> JobResponse:
    """Retry a failed job from scratch."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.FAILED:
        raise HTTPException(
            status_code=400,
            detail=f"Can only retry failed jobs. Current status: {job.status.value}",
        )

    # Reset job state
    job.status = JobStatus.PENDING
    job.current_stage = None
    job.stage_progress = 0
    job.error_message = None
    job.error_stage = None
    job.retry_count += 1
    db.commit()

    # Re-enqueue
    enqueue_job(job.id)

    return JobResponse.model_validate(job)


@router.get("/jobs/{job_id}/logs")
async def get_job_logs(
    job_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Get observability logs for a job.

    Returns timing information for each pipeline stage,
    useful for debugging and monitoring.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job_id,
        "status": job.status.value if job.status else None,
        "current_stage": job.current_stage.value if job.current_stage else None,
        "stage_progress": job.stage_progress,
        "stage_started_at": job.stage_started_at.isoformat() if job.stage_started_at else None,
        "stage_durations": job.stage_durations or {},
        "error_message": job.error_message,
        "error_stage": job.error_stage.value if job.error_stage else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.get("/jobs/{job_id}/artifacts")
async def get_job_artifacts(
    job_id: str,
) -> dict:
    """Get info about existing artifacts for a job.

    Useful for determining if a job can be resumed from a specific stage.
    """
    storage = get_storage_service()
    artifacts = storage.get_existing_artifacts(job_id)

    # Add counts for images and audio
    images = storage.list_images(job_id)
    audio = storage.list_audio(job_id)

    return {
        "job_id": job_id,
        "artifacts": artifacts,
        "image_count": len(images),
        "audio_count": len(audio),
        "image_segments": list(images.keys()),
        "audio_segments": list(audio.keys()),
    }


@router.post("/jobs/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(
    job_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> JobResponse:
    """Request cancellation of a processing job.

    The job will be cancelled at the next stage boundary.
    If the job is pending, it will be cancelled immediately.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status == JobStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Cannot cancel a completed job")

    if job.status == JobStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="Job is already cancelled")

    if job.status == JobStatus.FAILED:
        raise HTTPException(status_code=400, detail="Cannot cancel a failed job")

    if job.status == JobStatus.PENDING:
        # Cancel immediately if not yet started
        job.mark_cancelled()
        db.commit()
        return JobResponse.model_validate(job)

    # For processing jobs, set the cancel flag
    job.request_cancel()
    db.commit()

    return JobResponse.model_validate(job)


@router.post("/jobs/{job_id}/resume", response_model=JobResponse)
async def resume_job(
    job_id: str,
    db: Annotated[Session, Depends(get_db)],
    from_stage: str = "render",
) -> JobResponse:
    """Resume a failed job from a specific stage using existing artifacts.

    Args:
        job_id: Job to resume
        from_stage: Stage to resume from. Options:
            - 'images': Re-generate images, TTS, and render
            - 'tts': Re-generate TTS and render
            - 'render': Only re-run render (fastest, uses existing images/audio)
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.FAILED:
        raise HTTPException(
            status_code=400,
            detail=f"Can only resume failed jobs. Current status: {job.status.value}",
        )

    valid_stages = ["images", "tts", "render"]
    if from_stage not in valid_stages:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid stage. Must be one of: {valid_stages}",
        )

    # Check that required artifacts exist
    storage = get_storage_service()
    if not storage.has_timeline(job_id):
        raise HTTPException(
            status_code=400,
            detail="Cannot resume: timeline not found. Use /retry instead.",
        )

    if from_stage == "render":
        if not storage.has_audio(job_id):
            raise HTTPException(
                status_code=400,
                detail="Cannot resume from render: audio files not found. Try from_stage=tts",
            )

    # Reset job state
    job.status = JobStatus.PROCESSING
    job.error_message = None
    job.retry_count += 1
    db.commit()

    # Enqueue resume
    enqueue_resume(job_id, from_stage)

    return JobResponse.model_validate(job)
