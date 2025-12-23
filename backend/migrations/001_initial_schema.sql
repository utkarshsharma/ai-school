-- AI School Initial Schema
-- This migration creates the jobs table for PostgreSQL
-- Run with: psql -d ai_school -f 001_initial_schema.sql

-- Create job status enum type
DO $$ BEGIN
    CREATE TYPE job_status AS ENUM ('pending', 'processing', 'completed', 'failed');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Create job stage enum type
DO $$ BEGIN
    CREATE TYPE job_stage AS ENUM ('extract', 'generate', 'images', 'tts', 'render');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Create jobs table
CREATE TABLE IF NOT EXISTS jobs (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,

    -- Status tracking
    status job_status NOT NULL DEFAULT 'pending',
    current_stage job_stage,
    stage_progress INTEGER DEFAULT 0,

    -- Input
    original_filename VARCHAR(255) NOT NULL,
    pdf_path VARCHAR(512) NOT NULL,

    -- Artifacts (paths to generated files)
    timeline_path VARCHAR(512),
    audio_path VARCHAR(512),
    video_path VARCHAR(512),

    -- Metadata
    video_duration_seconds REAL,
    slide_count INTEGER,

    -- Error tracking
    error_message TEXT,
    error_stage job_stage,
    retry_count INTEGER DEFAULT 0
);

-- Create index on status for efficient job listing
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);

-- Create index on created_at for sorted listing
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);
