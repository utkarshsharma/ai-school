"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings from environment variables."""

    # API Keys
    gemini_api_key: str
    google_tts_api_key: str

    # Service URLs
    remotion_service_url: str = "http://localhost:3000"

    # Storage
    storage_base_path: Path = Path("./storage")
    database_url: str = "sqlite:///./storage/ai_school.db"

    # Server
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    debug: bool = False

    # Video settings
    video_fps: int = 30
    video_width: int = 1920
    video_height: int = 1080

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @property
    def pdf_path(self) -> Path:
        return self.storage_base_path / "pdfs"

    @property
    def audio_path(self) -> Path:
        return self.storage_base_path / "audio"

    @property
    def images_path(self) -> Path:
        return self.storage_base_path / "images"

    @property
    def videos_path(self) -> Path:
        return self.storage_base_path / "videos"

    @property
    def timelines_path(self) -> Path:
        return self.storage_base_path / "timelines"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
