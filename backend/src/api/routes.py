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
from src.worker.processor import enqueue_job

router = APIRouter(prefix="/api", tags=["jobs"])


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
) -> None:
    """Delete a job and its artifacts."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Delete artifacts
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
    """Retry a failed job."""
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
