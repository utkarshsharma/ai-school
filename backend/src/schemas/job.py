"""Job-related schemas."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Job status."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobStage(str, Enum):
    """Pipeline stage."""

    EXTRACT = "extract"
    GENERATE = "generate"
    IMAGES = "images"
    TTS = "tts"
    RENDER = "render"


class JobCreate(BaseModel):
    """Request to create a new job."""

    filename: str = Field(..., min_length=1, description="Original PDF filename")


class JobResponse(BaseModel):
    """Job response returned by API."""

    id: str
    status: JobStatus
    current_stage: JobStage | None = None
    stage_progress: int = 0
    original_filename: str
    video_duration_seconds: float | None = None
    slide_count: int | None = None
    error_message: str | None = None
    error_stage: JobStage | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    # Observability fields
    stage_started_at: datetime | None = None
    stage_durations: dict[str, float] = Field(default_factory=dict)

    model_config = {"from_attributes": True}

    @classmethod
    def model_validate(cls, obj, **kwargs):
        """Custom validation to handle None stage_durations from DB."""
        # If stage_durations is None, convert to empty dict before validation
        if hasattr(obj, "stage_durations") and obj.stage_durations is None:
            obj.stage_durations = {}
        return super().model_validate(obj, **kwargs)


class JobListResponse(BaseModel):
    """Response for listing jobs."""

    jobs: list[JobResponse]
    total: int
    page: int
    page_size: int
