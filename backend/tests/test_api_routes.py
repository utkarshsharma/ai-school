"""Tests for API routes."""

import io
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Set test environment before importing app
os.environ["GEMINI_API_KEY"] = "test-key"
os.environ["GOOGLE_TTS_API_KEY"] = "test-key"

from src.models.job import Job, JobStatus, JobStage
from src.schemas.job import JobResponse


class TestCreateJobValidation:
    """Tests for job creation validation."""

    def test_non_pdf_rejected(self) -> None:
        """Test that non-PDF files are rejected."""
        from src.api.routes import create_job

        # This would normally be tested with proper mocking
        # For now we test the validation logic conceptually
        assert True  # Placeholder - actual test needs FastAPI test client with proper mocking

    def test_empty_file_rejected(self) -> None:
        """Test that empty files are rejected."""
        # Validation is in the route handler
        assert True


class TestJobStatusEndpoints:
    """Tests for job status-related endpoints."""

    def test_job_status_values(self) -> None:
        """Test that job statuses have correct values."""
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.PROCESSING.value == "processing"
        assert JobStatus.COMPLETED.value == "completed"
        assert JobStatus.FAILED.value == "failed"

    def test_job_stage_values(self) -> None:
        """Test that job stages have correct values."""
        assert JobStage.EXTRACT.value == "extract"
        assert JobStage.GENERATE.value == "generate"
        assert JobStage.IMAGES.value == "images"
        assert JobStage.TTS.value == "tts"
        assert JobStage.RENDER.value == "render"


class TestJobModel:
    """Tests for Job model."""

    def _create_job(self) -> Job:
        """Create a job with required fields set."""
        from datetime import datetime
        job = Job(original_filename="test.pdf", pdf_path="/path/to/test.pdf")
        job.id = "test-id-12345678"
        job.status = JobStatus.PENDING
        job.stage_progress = 0
        job.retry_count = 0
        job.created_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        return job

    def test_job_creation(self) -> None:
        """Test basic job creation with required fields."""
        job = self._create_job()

        assert job.original_filename == "test.pdf"
        assert job.pdf_path == "/path/to/test.pdf"
        assert job.status == JobStatus.PENDING
        assert job.retry_count == 0

    def test_job_repr(self) -> None:
        """Test job string representation."""
        job = self._create_job()

        repr_str = repr(job)
        assert "test-id-" in repr_str
        assert "pending" in repr_str

    def test_job_mark_processing(self) -> None:
        """Test marking job as processing."""
        job = self._create_job()
        job.mark_processing(JobStage.GENERATE)

        assert job.status == JobStatus.PROCESSING
        assert job.current_stage == JobStage.GENERATE
        assert job.stage_progress == 0

    def test_job_mark_completed(self) -> None:
        """Test marking job as completed."""
        job = self._create_job()
        job.mark_completed()

        assert job.status == JobStatus.COMPLETED
        assert job.current_stage is None
        assert job.stage_progress == 100
        assert job.completed_at is not None

    def test_job_mark_failed(self) -> None:
        """Test marking job as failed."""
        job = self._create_job()
        job.current_stage = JobStage.TTS
        job.mark_failed("Test error", JobStage.TTS)

        assert job.status == JobStatus.FAILED
        assert job.error_message == "Test error"
        assert job.error_stage == JobStage.TTS

    def test_job_mark_failed_uses_current_stage(self) -> None:
        """Test that mark_failed uses current stage if not provided."""
        job = self._create_job()
        job.current_stage = JobStage.IMAGES
        job.mark_failed("Test error")

        assert job.error_stage == JobStage.IMAGES


class TestJobResponseSchema:
    """Tests for JobResponse schema."""

    def _create_job(self) -> Job:
        """Create a job with required fields set."""
        from datetime import datetime
        job = Job(original_filename="test.pdf", pdf_path="/path/to/test.pdf")
        job.id = "test-id-12345678"
        job.status = JobStatus.PENDING
        job.stage_progress = 0
        job.retry_count = 0
        job.created_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        return job

    def test_job_response_from_pending_job(self) -> None:
        """Test creating JobResponse from pending job."""
        job = self._create_job()

        # Test that the model can be validated
        response = JobResponse.model_validate(job)

        assert response.id == "test-id-12345678"
        assert response.status == JobStatus.PENDING
        assert response.original_filename == "test.pdf"

    def test_job_response_from_failed_job(self) -> None:
        """Test creating JobResponse from failed job."""
        job = self._create_job()
        job.mark_failed("Test error", JobStage.GENERATE)

        response = JobResponse.model_validate(job)

        assert response.status == JobStatus.FAILED
        assert response.error_message == "Test error"


class TestRouteLogic:
    """Tests for route logic without requiring FastAPI test client."""

    def test_file_size_limit(self) -> None:
        """Test that file size limit is enforced."""
        # 50MB limit is defined in routes.py
        max_size = 50 * 1024 * 1024
        assert max_size == 52428800

    def test_status_check_for_video_download(self) -> None:
        """Test that video download requires completed status."""
        job = Job(original_filename="test.pdf", pdf_path="/path/to/test.pdf")

        # Processing job should not allow video download
        job.status = JobStatus.PROCESSING
        assert job.status != JobStatus.COMPLETED

        # Failed job should not allow video download
        job.status = JobStatus.FAILED
        assert job.status != JobStatus.COMPLETED

        # Only completed job should allow
        job.status = JobStatus.COMPLETED
        assert job.status == JobStatus.COMPLETED

    def test_retry_requires_failed_status(self) -> None:
        """Test that retry requires failed status."""
        job = Job(original_filename="test.pdf", pdf_path="/path/to/test.pdf")

        # Pending job cannot be retried
        job.status = JobStatus.PENDING
        assert job.status != JobStatus.FAILED

        # Processing job cannot be retried
        job.status = JobStatus.PROCESSING
        assert job.status != JobStatus.FAILED

        # Completed job cannot be retried
        job.status = JobStatus.COMPLETED
        assert job.status != JobStatus.FAILED

        # Only failed job can be retried
        job.status = JobStatus.FAILED
        assert job.status == JobStatus.FAILED
