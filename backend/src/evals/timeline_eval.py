"""Timeline validation and evaluation layer.

This module implements deterministic evaluation that runs after every
Gemini call and before persistence/rendering. If validation fails,
the job must fail and be regenerated.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from src.schemas.timeline import Timeline

logger = logging.getLogger(__name__)


@dataclass
class EvalResult:
    """Result of timeline evaluation."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.valid


class TimelineEvalError(Exception):
    """Raised when timeline validation fails."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Timeline validation failed: {'; '.join(errors)}")


def evaluate_timeline(raw_data: dict[str, Any], job_id: str) -> Timeline:
    """Evaluate and validate timeline data from Gemini.

    This function implements the mandatory eval layer that runs after
    every Gemini call. It performs:
    1. Strict schema validation
    2. Timing invariants (monotonic, no overlaps)
    3. Required fields non-empty
    4. Content quality checks

    Args:
        raw_data: Raw JSON data from Gemini
        job_id: Job ID for logging

    Returns:
        Validated Timeline object

    Raises:
        TimelineEvalError: If any validation fails
    """
    logger.info(f"[{job_id}] Starting timeline evaluation")

    errors: list[str] = []
    warnings: list[str] = []

    # Check required top-level fields
    required_fields = ["title", "topic_summary", "target_age_group",
                       "total_duration_seconds", "segments"]
    for field_name in required_fields:
        if field_name not in raw_data:
            errors.append(f"Missing required field: {field_name}")

    if errors:
        raise TimelineEvalError(errors)

    # Validate segments exist and are a list
    segments = raw_data.get("segments", [])
    if not isinstance(segments, list):
        errors.append("segments must be a list")
        raise TimelineEvalError(errors)

    if len(segments) < 3:
        errors.append(f"Too few segments: {len(segments)} (minimum 3)")
    if len(segments) > 20:
        errors.append(f"Too many segments: {len(segments)} (maximum 20)")

    # Validate each segment
    expected_start = 0.0
    for i, seg in enumerate(segments):
        seg_id = seg.get("segment_id", f"segment_{i}")
        prefix = f"Segment {i+1} ({seg_id})"

        # Check segment_id format
        expected_id = f"seg_{i+1:03d}"
        if seg.get("segment_id") != expected_id:
            errors.append(f"{prefix}: ID should be {expected_id}, got {seg.get('segment_id')}")

        # Check timing
        start_time = seg.get("start_time_seconds", 0)
        duration = seg.get("duration_seconds", 0)

        if abs(start_time - expected_start) > 0.1:
            errors.append(
                f"{prefix}: start_time should be {expected_start}, got {start_time}"
            )

        if duration < 5:
            errors.append(f"{prefix}: duration too short ({duration}s, min 5s)")
        if duration > 120:
            errors.append(f"{prefix}: duration too long ({duration}s, max 120s)")

        expected_start = start_time + duration

        # Check slide content
        slide = seg.get("slide", {})
        if not slide.get("title"):
            errors.append(f"{prefix}: slide.title is empty")
        if not slide.get("bullets"):
            errors.append(f"{prefix}: slide.bullets is empty")
        elif len(slide.get("bullets", [])) < 1:
            errors.append(f"{prefix}: slide.bullets must have at least 1 bullet")
        if not slide.get("visual_prompt"):
            errors.append(f"{prefix}: slide.visual_prompt is empty")

        # Check narration
        narration = seg.get("narration_text", "")
        if not narration:
            errors.append(f"{prefix}: narration_text is empty")
        elif len(narration.split()) < 30:
            warnings.append(f"{prefix}: narration_text is short ({len(narration.split())} words)")

    # Check total duration consistency
    total_declared = raw_data.get("total_duration_seconds", 0)
    total_calculated = sum(s.get("duration_seconds", 0) for s in segments)

    if abs(total_declared - total_calculated) > 0.5:
        errors.append(
            f"total_duration_seconds ({total_declared}) doesn't match "
            f"sum of segments ({total_calculated})"
        )

    # Duration limits
    if total_calculated < 180:  # 3 minutes
        errors.append(f"Video too short: {total_calculated}s (minimum 180s)")
    if total_calculated > 900:  # 15 minutes
        errors.append(f"Video too long: {total_calculated}s (maximum 900s)")

    # Log warnings
    for warning in warnings:
        logger.warning(f"[{job_id}] {warning}")

    # Fail if any errors
    if errors:
        for error in errors:
            logger.error(f"[{job_id}] Eval error: {error}")
        raise TimelineEvalError(errors)

    # Now validate with Pydantic schema
    try:
        timeline = Timeline.model_validate(raw_data)
        timeline.validate_consistency()
    except Exception as e:
        logger.error(f"[{job_id}] Schema validation error: {e}")
        raise TimelineEvalError([str(e)]) from e

    logger.info(
        f"[{job_id}] Timeline evaluation passed: "
        f"{len(timeline.segments)} segments, {timeline.total_duration_seconds:.1f}s"
    )

    return timeline
