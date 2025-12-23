"""Job model for tracking video generation tasks."""

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Column, DateTime, Enum as SQLEnum, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

from src.models.database import Base


class JobStatus(str, Enum):
    """Job status enumeration."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobStage(str, Enum):
    """Pipeline stage enumeration."""

    EXTRACT = "extract"  # PDF text extraction
    GENERATE = "generate"  # Gemini content generation
    IMAGES = "images"  # Slide image generation
    TTS = "tts"  # Text-to-speech
    RENDER = "render"  # Remotion video rendering


class Job(Base):
    """Job model representing a video generation task."""

    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    # Status tracking
    status = Column(SQLEnum(JobStatus), default=JobStatus.PENDING, nullable=False)
    current_stage = Column(SQLEnum(JobStage), nullable=True)
    stage_progress = Column(Integer, default=0)  # 0-100

    # Observability - timing per stage
    stage_started_at = Column(DateTime, nullable=True)
    stage_durations = Column(JSON, default=dict)  # {"extract": 1.2, "generate": 45.3, ...}

    # Input
    original_filename = Column(String(255), nullable=False)
    pdf_path = Column(String(512), nullable=False)

    # Artifacts (paths to generated files)
    timeline_path = Column(String(512), nullable=True)  # Immutable timeline JSON
    audio_path = Column(String(512), nullable=True)
    video_path = Column(String(512), nullable=True)

    # Metadata
    video_duration_seconds = Column(Float, nullable=True)
    slide_count = Column(Integer, nullable=True)

    # Error tracking
    error_message = Column(Text, nullable=True)
    error_stage = Column(SQLEnum(JobStage), nullable=True)
    retry_count = Column(Integer, default=0)

    # Cancellation flag - checked between pipeline stages
    cancel_requested = Column(Integer, default=0)  # 0=false, 1=true (SQLite compat)

    def __repr__(self) -> str:
        return f"<Job {self.id[:8]} status={self.status.value}>"

    def mark_processing(self, stage: JobStage) -> None:
        """Mark job as processing a specific stage."""
        self.status = JobStatus.PROCESSING
        self.current_stage = stage
        self.stage_progress = 0
        self.updated_at = datetime.utcnow()

    def mark_completed(self) -> None:
        """Mark job as completed."""
        self.status = JobStatus.COMPLETED
        self.current_stage = None
        self.stage_progress = 100
        self.completed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def mark_failed(self, error: str, stage: JobStage | None = None) -> None:
        """Mark job as failed with error details."""
        self.status = JobStatus.FAILED
        self.error_message = error
        self.error_stage = stage or self.current_stage
        self.updated_at = datetime.utcnow()

    def mark_cancelled(self) -> None:
        """Mark job as cancelled."""
        self.status = JobStatus.CANCELLED
        self.cancel_requested = 0  # Reset flag
        self.updated_at = datetime.utcnow()

    def request_cancel(self) -> None:
        """Request cancellation - will be processed between stages."""
        self.cancel_requested = 1
        self.updated_at = datetime.utcnow()
