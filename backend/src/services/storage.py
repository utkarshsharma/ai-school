"""Storage service for managing file artifacts.

Abstracts filesystem operations behind an interface that can be
swapped for cloud storage (S3/Supabase) in future versions.
"""

import shutil
from pathlib import Path

from src.config import get_settings


class StorageService:
    """Local filesystem storage service."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Ensure all storage directories exist."""
        self._settings.pdf_path.mkdir(parents=True, exist_ok=True)
        self._settings.audio_path.mkdir(parents=True, exist_ok=True)
        self._settings.images_path.mkdir(parents=True, exist_ok=True)
        self._settings.videos_path.mkdir(parents=True, exist_ok=True)
        self._settings.timelines_path.mkdir(parents=True, exist_ok=True)

    @property
    def base_path(self) -> Path:
        return self._settings.storage_base_path

    def save_pdf(self, job_id: str, content: bytes, filename: str) -> Path:
        """Save uploaded PDF file.

        Args:
            job_id: Job identifier
            content: PDF file bytes
            filename: Original filename

        Returns:
            Path to saved file
        """
        job_dir = self._settings.pdf_path / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        # Sanitize filename and save
        safe_filename = Path(filename).name  # Remove any path components
        file_path = job_dir / safe_filename
        file_path.write_bytes(content)

        return file_path

    def get_pdf_path(self, job_id: str, filename: str) -> Path:
        """Get path to a stored PDF."""
        return self._settings.pdf_path / job_id / Path(filename).name

    def save_timeline(self, job_id: str, content: str) -> Path:
        """Save timeline JSON.

        Args:
            job_id: Job identifier
            content: Timeline JSON string

        Returns:
            Path to saved file
        """
        file_path = self._settings.timelines_path / f"{job_id}.json"
        file_path.write_text(content, encoding="utf-8")
        return file_path

    def get_timeline_path(self, job_id: str) -> Path:
        """Get path to timeline JSON."""
        return self._settings.timelines_path / f"{job_id}.json"

    def save_audio(self, job_id: str, segment_id: str, content: bytes) -> Path:
        """Save audio segment.

        Args:
            job_id: Job identifier
            segment_id: Segment identifier
            content: Audio file bytes

        Returns:
            Path to saved file
        """
        job_dir = self._settings.audio_path / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        file_path = job_dir / f"{segment_id}.mp3"
        file_path.write_bytes(content)
        return file_path

    def get_audio_dir(self, job_id: str) -> Path:
        """Get directory for job's audio files."""
        return self._settings.audio_path / job_id

    def save_image(self, job_id: str, segment_id: str, content: bytes) -> Path:
        """Save slide image.

        Args:
            job_id: Job identifier
            segment_id: Segment identifier
            content: Image file bytes

        Returns:
            Path to saved file
        """
        job_dir = self._settings.images_path / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        file_path = job_dir / f"{segment_id}.png"
        file_path.write_bytes(content)
        return file_path

    def get_images_dir(self, job_id: str) -> Path:
        """Get directory for job's image files."""
        return self._settings.images_path / job_id

    def get_video_path(self, job_id: str) -> Path:
        """Get path for output video."""
        return self._settings.videos_path / f"{job_id}.mp4"

    def delete_job_artifacts(self, job_id: str) -> None:
        """Delete all artifacts for a job.

        Args:
            job_id: Job identifier
        """
        paths_to_delete = [
            self._settings.pdf_path / job_id,
            self._settings.audio_path / job_id,
            self._settings.images_path / job_id,
            self._settings.timelines_path / f"{job_id}.json",
            self._settings.videos_path / f"{job_id}.mp4",
        ]

        for path in paths_to_delete:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            elif path.is_file():
                path.unlink(missing_ok=True)


# Singleton instance
_storage_service: StorageService | None = None


def get_storage_service() -> StorageService:
    """Get storage service singleton."""
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service
