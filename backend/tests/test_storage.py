"""Tests for storage service."""

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.services.storage import StorageService


class TestStorageService:
    """Tests for StorageService."""

    @pytest.fixture
    def storage(self, tmp_path: Path) -> StorageService:
        """Create storage service with temp directory."""
        mock_settings = MagicMock()
        mock_settings.storage_base_path = tmp_path
        mock_settings.pdf_path = tmp_path / "pdfs"
        mock_settings.audio_path = tmp_path / "audio"
        mock_settings.images_path = tmp_path / "images"
        mock_settings.videos_path = tmp_path / "videos"
        mock_settings.timelines_path = tmp_path / "timelines"

        with patch("src.services.storage.get_settings", return_value=mock_settings):
            return StorageService()

    def test_init_creates_directories(self, storage: StorageService) -> None:
        """Test that initialization creates required directories."""
        base = storage.base_path
        assert (base / "pdfs").exists()
        assert (base / "audio").exists()
        assert (base / "images").exists()
        assert (base / "videos").exists()
        assert (base / "timelines").exists()

    def test_save_pdf(self, storage: StorageService) -> None:
        """Test saving PDF file."""
        job_id = "test-job-001"
        content = b"%PDF-1.4 Test PDF content"
        filename = "test_document.pdf"

        path = storage.save_pdf(job_id, content, filename)

        assert path.exists()
        assert path.read_bytes() == content
        assert path.name == filename
        assert job_id in str(path)

    def test_save_pdf_sanitizes_filename(self, storage: StorageService) -> None:
        """Test that save_pdf sanitizes filenames with path components."""
        job_id = "test-job-002"
        content = b"PDF content"
        # Attempt path traversal
        filename = "../../../malicious.pdf"

        path = storage.save_pdf(job_id, content, filename)

        # Should only keep the base filename
        assert path.name == "malicious.pdf"
        assert ".." not in str(path)

    def test_get_pdf_path(self, storage: StorageService) -> None:
        """Test getting PDF path."""
        path = storage.get_pdf_path("job-123", "doc.pdf")

        assert "job-123" in str(path)
        assert path.name == "doc.pdf"

    def test_save_timeline(self, storage: StorageService) -> None:
        """Test saving timeline JSON."""
        job_id = "test-job-003"
        content = '{"title": "Test Timeline", "segments": []}'

        path = storage.save_timeline(job_id, content)

        assert path.exists()
        assert path.read_text() == content
        assert path.suffix == ".json"
        assert job_id in path.name

    def test_get_timeline_path(self, storage: StorageService) -> None:
        """Test getting timeline path."""
        path = storage.get_timeline_path("job-456")

        assert path.name == "job-456.json"
        assert "timelines" in str(path)

    def test_save_audio(self, storage: StorageService) -> None:
        """Test saving audio segment."""
        job_id = "test-job-004"
        segment_id = "seg_001"
        content = b"fake mp3 data"

        path = storage.save_audio(job_id, segment_id, content)

        assert path.exists()
        assert path.read_bytes() == content
        assert path.suffix == ".mp3"
        assert segment_id in path.name

    def test_get_audio_dir(self, storage: StorageService) -> None:
        """Test getting audio directory."""
        path = storage.get_audio_dir("job-789")

        assert "job-789" in str(path)
        assert "audio" in str(path)

    def test_save_image(self, storage: StorageService) -> None:
        """Test saving slide image."""
        job_id = "test-job-005"
        segment_id = "seg_002"
        # Minimal valid PNG
        content = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        )

        path = storage.save_image(job_id, segment_id, content)

        assert path.exists()
        assert path.read_bytes() == content
        assert path.suffix == ".png"
        assert segment_id in path.name

    def test_get_images_dir(self, storage: StorageService) -> None:
        """Test getting images directory."""
        path = storage.get_images_dir("job-abc")

        assert "job-abc" in str(path)
        assert "images" in str(path)

    def test_get_video_path(self, storage: StorageService) -> None:
        """Test getting video path."""
        path = storage.get_video_path("job-xyz")

        assert path.name == "job-xyz.mp4"
        assert "videos" in str(path)

    def test_delete_job_artifacts(self, storage: StorageService) -> None:
        """Test deleting all job artifacts."""
        job_id = "test-job-delete"

        # Create various artifacts
        storage.save_pdf(job_id, b"pdf content", "test.pdf")
        storage.save_timeline(job_id, '{"test": true}')
        storage.save_audio(job_id, "seg_001", b"audio")
        storage.save_image(job_id, "seg_001", b"image")

        # Create video path and write to it
        video_path = storage.get_video_path(job_id)
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.write_bytes(b"fake video")

        # Verify artifacts exist
        assert storage.get_timeline_path(job_id).exists()
        assert video_path.exists()

        # Delete all
        storage.delete_job_artifacts(job_id)

        # Verify deletion
        assert not storage.get_timeline_path(job_id).exists()
        assert not video_path.exists()

    def test_delete_job_artifacts_handles_missing(self, storage: StorageService) -> None:
        """Test that delete_job_artifacts handles missing files gracefully."""
        job_id = "nonexistent-job"

        # Should not raise any errors
        storage.delete_job_artifacts(job_id)

    def test_multiple_jobs_isolated(self, storage: StorageService) -> None:
        """Test that artifacts from different jobs are isolated."""
        job1 = "job-one"
        job2 = "job-two"

        storage.save_pdf(job1, b"pdf1", "doc1.pdf")
        storage.save_pdf(job2, b"pdf2", "doc2.pdf")

        # Delete job1 artifacts
        storage.delete_job_artifacts(job1)

        # Job2 should still exist
        pdf2_path = storage.get_pdf_path(job2, "doc2.pdf")
        assert pdf2_path.exists()
