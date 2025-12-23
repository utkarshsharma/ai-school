-- AI School Cancel Job Support
-- Adds cancel_requested column for graceful job cancellation
-- Run with: psql -d ai_school -f 003_add_cancel_column.sql

-- Add cancel_requested flag (0 = false, 1 = true for SQLite compatibility)
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS cancel_requested INTEGER DEFAULT 0;

-- Update job_status enum to include 'cancelled' (PostgreSQL only)
-- For existing PostgreSQL installations, run:
-- ALTER TYPE job_status ADD VALUE IF NOT EXISTS 'cancelled';
