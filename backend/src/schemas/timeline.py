"""Timeline schema - the immutable contract between Gemini and Remotion.

This schema defines the authoritative structure for video generation.
All downstream steps (audio, rendering) must strictly follow this timeline.
If validation fails, the job must fail and be regenerated.
"""

from pydantic import BaseModel, Field, field_validator


class Slide(BaseModel):
    """Visual content for a single slide."""

    title: str = Field(..., min_length=1, max_length=100, description="Slide title/headline")
    bullets: list[str] = Field(
        ..., min_length=1, max_length=5, description="Key points (1-5 bullets)"
    )
    visual_prompt: str = Field(
        ...,
        min_length=10,
        max_length=500,
        description="Prompt for generating slide background image",
    )

    @field_validator("bullets")
    @classmethod
    def validate_bullets(cls, v: list[str]) -> list[str]:
        if not all(bullet.strip() for bullet in v):
            raise ValueError("All bullets must be non-empty")
        return [bullet.strip() for bullet in v]


class TimelineSegment(BaseModel):
    """A single segment in the video timeline.

    Each segment corresponds to one slide and one narration audio clip.
    Duration is authoritative - audio must be generated to match.
    """

    segment_id: str = Field(..., pattern=r"^seg_\d{3}$", description="Segment ID (e.g., seg_001)")
    start_time_seconds: float = Field(..., ge=0, description="Start time in seconds")
    duration_seconds: float = Field(
        ..., gt=5, le=120, description="Duration in seconds (5-120)"
    )
    slide: Slide = Field(..., description="Visual content for this segment")
    narration_text: str = Field(
        ..., min_length=50, max_length=2000, description="Teacher training narration script"
    )

    @property
    def end_time_seconds(self) -> float:
        return self.start_time_seconds + self.duration_seconds


class Timeline(BaseModel):
    """Complete video timeline - immutable and authoritative.

    This is the contract between content generation and rendering.
    All downstream steps must strictly follow this timeline.
    """

    version: str = Field(default="1.0", description="Schema version")
    title: str = Field(..., min_length=1, max_length=200, description="Video title")
    topic_summary: str = Field(
        ..., min_length=50, max_length=500, description="Brief topic summary"
    )
    target_age_group: str = Field(
        ..., description="Target student age group (e.g., '10-12 years')"
    )
    total_duration_seconds: float = Field(
        ..., gt=0, le=900, description="Total video duration (max 15 minutes)"
    )
    segments: list[TimelineSegment] = Field(
        ..., min_length=3, max_length=20, description="Video segments"
    )

    @field_validator("segments")
    @classmethod
    def validate_segments(cls, v: list[TimelineSegment]) -> list[TimelineSegment]:
        """Validate segment ordering and timing."""
        if not v:
            raise ValueError("At least one segment required")

        # Check monotonic ordering
        for i, seg in enumerate(v):
            expected_id = f"seg_{i + 1:03d}"
            if seg.segment_id != expected_id:
                raise ValueError(f"Segment {i} has ID {seg.segment_id}, expected {expected_id}")

        # Check no overlaps and continuous timeline
        for i in range(1, len(v)):
            prev_end = v[i - 1].end_time_seconds
            curr_start = v[i].start_time_seconds
            if abs(curr_start - prev_end) > 0.01:  # Allow tiny float tolerance
                raise ValueError(
                    f"Gap or overlap between segment {i-1} (ends {prev_end}) "
                    f"and segment {i} (starts {curr_start})"
                )

        return v

    @field_validator("total_duration_seconds")
    @classmethod
    def validate_duration(cls, v: float) -> float:
        """Validate total duration is reasonable for teacher training."""
        if v < 180:  # Less than 3 minutes
            raise ValueError("Video too short (minimum 3 minutes)")
        if v > 900:  # More than 15 minutes
            raise ValueError("Video too long (maximum 15 minutes)")
        return v

    def validate_consistency(self) -> None:
        """Validate timeline internal consistency.

        Raises ValueError if any invariants are violated.
        Called after initial validation to catch additional issues.
        """
        # Sum of segment durations should match total
        segment_total = sum(seg.duration_seconds for seg in self.segments)
        if abs(segment_total - self.total_duration_seconds) > 0.1:
            raise ValueError(
                f"Segment durations ({segment_total}s) don't match "
                f"total duration ({self.total_duration_seconds}s)"
            )

        # First segment should start at 0
        if self.segments and self.segments[0].start_time_seconds != 0:
            raise ValueError("First segment must start at time 0")
