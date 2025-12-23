-- AI School Observability Schema
-- Adds timing fields for stage-level observability
-- Run with: psql -d ai_school -f 002_add_observability.sql

-- Add timestamp for when current stage started
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS stage_started_at TIMESTAMP;

-- Add JSON field for stage durations (e.g., {"extract": 1.2, "generate": 45.3})
-- For PostgreSQL, use JSONB for efficient querying
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS stage_durations JSONB DEFAULT '{}';

-- Note: SQLite will use TEXT with JSON functions
-- SQLAlchemy handles this via JSON type
