"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import get_settings
from src.models import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    settings = get_settings()
    settings.storage_base_path.mkdir(parents=True, exist_ok=True)
    settings.pdf_path.mkdir(parents=True, exist_ok=True)
    settings.audio_path.mkdir(parents=True, exist_ok=True)
    settings.images_path.mkdir(parents=True, exist_ok=True)
    settings.videos_path.mkdir(parents=True, exist_ok=True)
    settings.timelines_path.mkdir(parents=True, exist_ok=True)
    init_db()
    yield
    # Shutdown


app = FastAPI(
    title="AI School - Teacher Training Video Generator",
    description="Generate teacher training videos from curriculum PDFs",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "ai-school-backend"}


# API routes will be added in Module 8
