"""Tests for background job worker/processor."""

from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime

import pytest

from src.worker.processor import (
    enqueue_job,
    enqueue_resume,
    start_worker,
    _process_job,
    _run_pipeline,
    _update_stage,
)
from src.queue.job_queue import get_job_queue, JobMessage, QueueBackend
from src.models.job import Job, JobStatus, JobStage
from src.services.pdf_extractor import PDFContent


def create_valid_timeline_data(num_segments: int = 3, segment_duration: float = 60.0) -> dict:
    """Create valid timeline data for testing."""
    segments = []
    start_time = 0.0

    for i in range(num_segments):
        segment = {
            "segment_id": f"seg_{i + 1:03d}",
            "start_time_seconds": start_time,
            "duration_seconds": segment_duration,
            "slide": {
                "title": f"Slide {i + 1}: Topic Title",
                "bullets": [f"Key point {i + 1}.1", f"Key point {i + 1}.2"],
                "visual_prompt": f"A clean, minimalist educational slide background for slide {i + 1}.",
            },
            "narration_text": (
                f"This is the narration for slide {i + 1}. "
                "It contains enough words to pass validation requirements. "
                "The teacher will explain key concepts clearly and concisely. "
                "This helps ensure proper pedagogical communication. "
                "Additional context and examples make learning more engaging. "
                "Students benefit from clear explanations and structured content."
            ),
        }
        segments.append(segment)
        start_time += segment_duration

    return {
        "version": "1.0",
        "title": "Teacher Training: Educational Topic",
        "topic_summary": (
            "This video covers important teaching strategies for educators. "
            "It includes practical examples and evidence-based approaches."
        ),
        "target_age_group": "10-12 years",
        "total_duration_seconds": num_segments * segment_duration,
        "segments": segments,
    }


class TestEnqueueJob:
    """Tests for enqueue_job function."""

    def test_enqueue_adds_to_queue(self) -> None:
        """Test that enqueue_job adds job ID to queue."""
        queue = get_job_queue()
        queue.clear()

        enqueue_job("test-job-123")

        assert queue.size() == 1
        message = queue.dequeue(timeout=1)
        assert message is not None
        assert message.job_id == "test-job-123"
        assert message.action == "process"

    def test_enqueue_multiple_jobs(self) -> None:
        """Test enqueueing multiple jobs."""
        queue = get_job_queue()
        queue.clear()

        enqueue_job("job-1")
        enqueue_job("job-2")
        enqueue_job("job-3")

        # Jobs should be in FIFO order
        msg1 = queue.dequeue(timeout=1)
        msg2 = queue.dequeue(timeout=1)
        msg3 = queue.dequeue(timeout=1)
        assert msg1.job_id == "job-1"
        assert msg2.job_id == "job-2"
        assert msg3.job_id == "job-3"

    def test_enqueue_resume_adds_to_queue(self) -> None:
        """Test that enqueue_resume adds resume message to queue."""
        queue = get_job_queue()
        queue.clear()

        enqueue_resume("job-resume-123", "render")

        assert queue.size() == 1
        message = queue.dequeue(timeout=1)
        assert message is not None
        assert message.job_id == "job-resume-123"
        assert message.action == "resume"
        assert message.from_stage == "render"


class TestStartWorker:
    """Tests for start_worker function."""

    def test_start_worker_creates_thread(self) -> None:
        """Test that start_worker creates a background thread."""
        import src.queue.job_queue as queue_module

        # Reset the worker thread
        queue_module._worker_thread = None

        with patch.object(queue_module, "_worker_loop") as mock_loop:
            start_worker()

            # Worker thread should exist
            assert queue_module._worker_thread is not None

    def test_start_worker_is_idempotent(self) -> None:
        """Test that starting worker twice doesn't create duplicate threads when first is alive."""
        import src.queue.job_queue as queue_module
        import threading

        # Create a mock thread that appears alive
        mock_thread = MagicMock(spec=threading.Thread)
        mock_thread.is_alive.return_value = True

        queue_module._worker_thread = mock_thread

        # Start worker - should not replace the existing alive thread
        start_worker()

        # Should still be the mock thread
        assert queue_module._worker_thread is mock_thread


class TestProcessJob:
    """Tests for _process_job function."""

    def test_process_job_not_found(self) -> None:
        """Test processing a non-existent job."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        mock_session_local = MagicMock(return_value=mock_session)

        with patch("src.worker.processor.get_session_local", return_value=mock_session_local):
            # Should not raise, just log error
            _process_job("nonexistent-job")

    def test_process_job_skips_non_pending(self) -> None:
        """Test that non-pending jobs are skipped."""
        mock_job = MagicMock()
        mock_job.id = "job-123"
        mock_job.status = JobStatus.PROCESSING  # Not pending

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_job

        mock_session_local = MagicMock(return_value=mock_session)

        with patch("src.worker.processor.get_session_local", return_value=mock_session_local):
            with patch("src.worker.processor._run_pipeline") as mock_pipeline:
                _process_job("job-123")

                # Pipeline should not be called
                mock_pipeline.assert_not_called()


class TestUpdateStage:
    """Tests for _update_stage function."""

    def test_update_stage_sets_fields(self) -> None:
        """Test that update_stage sets all expected fields."""
        mock_job = MagicMock()
        mock_db = MagicMock()

        _update_stage(mock_job, mock_db, JobStage.EXTRACT, 50)

        assert mock_job.status == JobStatus.PROCESSING
        assert mock_job.current_stage == JobStage.EXTRACT
        assert mock_job.stage_progress == 50
        mock_db.commit.assert_called_once()


class TestJobStatus:
    """Tests for Job status transitions."""

    def test_job_mark_processing(self) -> None:
        """Test marking job as processing."""
        job = Job(original_filename="test.pdf", pdf_path="/path/test.pdf")
        job.mark_processing(JobStage.GENERATE)

        assert job.status == JobStatus.PROCESSING
        assert job.current_stage == JobStage.GENERATE
        assert job.stage_progress == 0

    def test_job_mark_completed(self) -> None:
        """Test marking job as completed."""
        job = Job(original_filename="test.pdf", pdf_path="/path/test.pdf")
        job.mark_completed()

        assert job.status == JobStatus.COMPLETED
        assert job.current_stage is None
        assert job.stage_progress == 100
        assert job.completed_at is not None

    def test_job_mark_failed(self) -> None:
        """Test marking job as failed."""
        job = Job(original_filename="test.pdf", pdf_path="/path/test.pdf")
        job.current_stage = JobStage.TTS
        job.mark_failed("Error message", JobStage.TTS)

        assert job.status == JobStatus.FAILED
        assert job.error_message == "Error message"
        assert job.error_stage == JobStage.TTS

    def test_job_mark_failed_uses_current_stage(self) -> None:
        """Test marking job as failed uses current stage if not specified."""
        job = Job(original_filename="test.pdf", pdf_path="/path/test.pdf")
        job.current_stage = JobStage.IMAGES
        job.mark_failed("Error message")

        assert job.error_stage == JobStage.IMAGES
