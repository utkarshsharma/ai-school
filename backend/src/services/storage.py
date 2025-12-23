"""Storage service for managing file artifacts.

Abstracts filesystem operations behind an interface that can be
swapped for cloud storage (S3/Supabase) in future versions.
"""

import shutil
from pathlib import Path
from typing import Protocol

from src.config import get_settings


class StorageProtocol(Protocol):
    """Protocol defining the storage service interface.

    Any storage backend (local, S3, GCS) must implement these methods.
    This enables swapping storage implementations without changing consuming code.
    """

    @property
    def base_path(self) -> Path:
        """Get base storage path."""
        ...

    def save_pdf(self, job_id: str, content: bytes, filename: str) -> Path:
        """Save uploaded PDF file."""
        ...

    def get_pdf_path(self, job_id: str, filename: str) -> Path:
        """Get path to a stored PDF."""
        ...

    def save_timeline(self, job_id: str, content: str) -> Path:
        """Save timeline JSON."""
        ...

    def get_timeline_path(self, job_id: str) -> Path:
        """Get path to timeline JSON."""
        ...

    def save_audio(self, job_id: str, segment_id: str, content: bytes) -> Path:
        """Save audio segment."""
        ...

    def get_audio_dir(self, job_id: str) -> Path:
        """Get directory for job's audio files."""
        ...

    def save_image(self, job_id: str, segment_id: str, content: bytes) -> Path:
        """Save slide image."""
        ...

    def get_images_dir(self, job_id: str) -> Path:
        """Get directory for job's image files."""
        ...

    def get_video_path(self, job_id: str) -> Path:
        """Get path for output video."""
        ...

    def delete_job_artifacts(self, job_id: str) -> None:
        """Delete all artifacts for a job."""
        ...

    def has_timeline(self, job_id: str) -> bool:
        """Check if timeline JSON exists for job."""
        ...

    def has_images(self, job_id: str) -> bool:
        """Check if images directory exists and has files."""
        ...

    def has_audio(self, job_id: str) -> bool:
        """Check if audio directory exists and has files."""
        ...

    def load_timeline_json(self, job_id: str) -> str | None:
        """Load timeline JSON content if it exists."""
        ...

    def list_images(self, job_id: str) -> dict[str, Path]:
        """List all images for a job, keyed by segment_id."""
        ...

    def list_audio(self, job_id: str) -> dict[str, Path]:
        """List all audio files for a job, keyed by segment_id."""
        ...

    def get_existing_artifacts(self, job_id: str) -> dict[str, bool]:
        """Get summary of which artifacts exist for a job."""
        ...


class LocalStorageService:
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

    def has_timeline(self, job_id: str) -> bool:
        """Check if timeline JSON exists for job."""
        return self.get_timeline_path(job_id).exists()

    def has_images(self, job_id: str) -> bool:
        """Check if images directory exists and has files."""
        img_dir = self.get_images_dir(job_id)
        return img_dir.exists() and any(img_dir.glob("*.png"))

    def has_audio(self, job_id: str) -> bool:
        """Check if audio directory exists and has files."""
        audio_dir = self.get_audio_dir(job_id)
        return audio_dir.exists() and any(audio_dir.glob("*.mp3"))

    def load_timeline_json(self, job_id: str) -> str | None:
        """Load timeline JSON content if it exists."""
        timeline_path = self.get_timeline_path(job_id)
        if timeline_path.exists():
            return timeline_path.read_text(encoding="utf-8")
        return None

    def list_images(self, job_id: str) -> dict[str, Path]:
        """List all images for a job, keyed by segment_id."""
        img_dir = self.get_images_dir(job_id)
        if not img_dir.exists():
            return {}
        return {p.stem: p for p in img_dir.glob("*.png")}

    def list_audio(self, job_id: str) -> dict[str, Path]:
        """List all audio files for a job, keyed by segment_id."""
        audio_dir = self.get_audio_dir(job_id)
        if not audio_dir.exists():
            return {}
        return {p.stem: p for p in audio_dir.glob("*.mp3")}

    def get_existing_artifacts(self, job_id: str) -> dict[str, bool]:
        """Get summary of which artifacts exist for a job."""
        pdf_dir = self._settings.pdf_path / job_id
        return {
            "pdf": pdf_dir.exists() and any(pdf_dir.glob("*.pdf")),
            "timeline": self.has_timeline(job_id),
            "images": self.has_images(job_id),
            "audio": self.has_audio(job_id),
            "video": self.get_video_path(job_id).exists(),
        }


# Singleton instance
_storage_service: LocalStorageService | None = None


def get_storage_service() -> StorageProtocol:
    """Get storage service singleton.

    Returns a StorageProtocol implementation. Currently uses LocalStorageService,
    but can be swapped for cloud storage in production.
    """
    global _storage_service
    if _storage_service is None:
        _storage_service = LocalStorageService()
    return _storage_service


# Backwards compatibility alias
StorageService = LocalStorageService
