"""Tests for timeline evaluation and validation."""

import pytest

from src.evals.timeline_eval import (
    evaluate_timeline,
    TimelineEvalError,
    EvalResult,
)
from src.schemas.timeline import Timeline


def create_valid_timeline_data(num_segments: int = 3, segment_duration: float = 60.0) -> dict:
    """Create valid timeline data for testing."""
    segments = []
    start_time = 0.0

    for i in range(num_segments):
        segment = {
            "segment_id": f"seg_{i + 1:03d}",
            "start_time_seconds": start_time,
            "duration_seconds": segment_duration,
            "slide": {
                "title": f"Slide {i + 1}: Topic Title",
                "bullets": [
                    f"Key point {i + 1}.1",
                    f"Key point {i + 1}.2",
                ],
                "visual_prompt": f"A clean, minimalist educational slide background for slide {i + 1} with subtle visual elements.",
            },
            "narration_text": (
                f"This is the narration for slide {i + 1}. "
                "It contains enough words to pass validation requirements. "
                "The teacher will explain key concepts clearly and concisely. "
                "This helps ensure proper pedagogical communication. "
                "Additional context and examples make learning more engaging. "
                "Students benefit from clear explanations and structured content."
            ),
        }
        segments.append(segment)
        start_time += segment_duration

    return {
        "version": "1.0",
        "title": "Teacher Training: Educational Topic",
        "topic_summary": (
            "This video covers important teaching strategies for educators. "
            "It includes practical examples and evidence-based approaches to help "
            "teachers effectively communicate complex concepts to students."
        ),
        "target_age_group": "10-12 years",
        "total_duration_seconds": num_segments * segment_duration,
        "segments": segments,
    }


class TestTimelineEval:
    """Tests for timeline evaluation."""

    def test_valid_timeline_passes(self) -> None:
        """Test that a valid timeline passes evaluation."""
        data = create_valid_timeline_data(num_segments=3, segment_duration=60.0)
        timeline = evaluate_timeline(data, "test-job-001")

        assert isinstance(timeline, Timeline)
        assert len(timeline.segments) == 3
        assert timeline.total_duration_seconds == 180.0

    def test_missing_title_fails(self) -> None:
        """Test that missing title field fails."""
        data = create_valid_timeline_data()
        del data["title"]

        with pytest.raises(TimelineEvalError) as exc_info:
            evaluate_timeline(data, "test-job")

        assert "Missing required field: title" in str(exc_info.value)

    def test_missing_topic_summary_fails(self) -> None:
        """Test that missing topic_summary field fails."""
        data = create_valid_timeline_data()
        del data["topic_summary"]

        with pytest.raises(TimelineEvalError) as exc_info:
            evaluate_timeline(data, "test-job")

        assert "Missing required field: topic_summary" in str(exc_info.value)

    def test_missing_segments_fails(self) -> None:
        """Test that missing segments field fails."""
        data = create_valid_timeline_data()
        del data["segments"]

        with pytest.raises(TimelineEvalError) as exc_info:
            evaluate_timeline(data, "test-job")

        assert "Missing required field: segments" in str(exc_info.value)

    def test_too_few_segments_fails(self) -> None:
        """Test that fewer than 3 segments fails."""
        data = create_valid_timeline_data(num_segments=2, segment_duration=100.0)

        with pytest.raises(TimelineEvalError) as exc_info:
            evaluate_timeline(data, "test-job")

        assert "Too few segments: 2" in str(exc_info.value)

    def test_too_many_segments_fails(self) -> None:
        """Test that more than 20 segments fails."""
        data = create_valid_timeline_data(num_segments=21, segment_duration=10.0)

        with pytest.raises(TimelineEvalError) as exc_info:
            evaluate_timeline(data, "test-job")

        assert "Too many segments: 21" in str(exc_info.value)

    def test_wrong_segment_id_fails(self) -> None:
        """Test that wrong segment ID fails."""
        data = create_valid_timeline_data()
        data["segments"][1]["segment_id"] = "wrong_id"

        with pytest.raises(TimelineEvalError) as exc_info:
            evaluate_timeline(data, "test-job")

        assert "ID should be seg_002" in str(exc_info.value)

    def test_wrong_start_time_fails(self) -> None:
        """Test that incorrect start time fails."""
        data = create_valid_timeline_data()
        data["segments"][1]["start_time_seconds"] = 100.0  # Should be 60.0

        with pytest.raises(TimelineEvalError) as exc_info:
            evaluate_timeline(data, "test-job")

        assert "start_time should be" in str(exc_info.value)

    def test_duration_too_short_fails(self) -> None:
        """Test that segment duration under 5s fails."""
        data = create_valid_timeline_data()
        data["segments"][0]["duration_seconds"] = 3.0
        # Need to recalculate total and adjust start times
        data["total_duration_seconds"] = 3.0 + 60.0 + 60.0
        data["segments"][1]["start_time_seconds"] = 3.0
        data["segments"][2]["start_time_seconds"] = 63.0

        with pytest.raises(TimelineEvalError) as exc_info:
            evaluate_timeline(data, "test-job")

        assert "duration too short" in str(exc_info.value)

    def test_duration_too_long_fails(self) -> None:
        """Test that segment duration over 120s fails."""
        data = create_valid_timeline_data(num_segments=3, segment_duration=100.0)
        data["segments"][0]["duration_seconds"] = 150.0
        # Recalculate
        data["segments"][1]["start_time_seconds"] = 150.0
        data["segments"][2]["start_time_seconds"] = 250.0
        data["total_duration_seconds"] = 150.0 + 100.0 + 100.0

        with pytest.raises(TimelineEvalError) as exc_info:
            evaluate_timeline(data, "test-job")

        assert "duration too long" in str(exc_info.value)

    def test_empty_slide_title_fails(self) -> None:
        """Test that empty slide title fails."""
        data = create_valid_timeline_data()
        data["segments"][0]["slide"]["title"] = ""

        with pytest.raises(TimelineEvalError) as exc_info:
            evaluate_timeline(data, "test-job")

        assert "slide.title is empty" in str(exc_info.value)

    def test_empty_bullets_fails(self) -> None:
        """Test that empty bullets list fails."""
        data = create_valid_timeline_data()
        data["segments"][0]["slide"]["bullets"] = []

        with pytest.raises(TimelineEvalError) as exc_info:
            evaluate_timeline(data, "test-job")

        assert "slide.bullets is empty" in str(exc_info.value)

    def test_empty_visual_prompt_fails(self) -> None:
        """Test that empty visual prompt fails."""
        data = create_valid_timeline_data()
        data["segments"][0]["slide"]["visual_prompt"] = ""

        with pytest.raises(TimelineEvalError) as exc_info:
            evaluate_timeline(data, "test-job")

        assert "slide.visual_prompt is empty" in str(exc_info.value)

    def test_empty_narration_fails(self) -> None:
        """Test that empty narration text fails."""
        data = create_valid_timeline_data()
        data["segments"][0]["narration_text"] = ""

        with pytest.raises(TimelineEvalError) as exc_info:
            evaluate_timeline(data, "test-job")

        assert "narration_text is empty" in str(exc_info.value)

    def test_duration_mismatch_fails(self) -> None:
        """Test that mismatched total duration fails."""
        data = create_valid_timeline_data()
        data["total_duration_seconds"] = 200.0  # Should be 180.0

        with pytest.raises(TimelineEvalError) as exc_info:
            evaluate_timeline(data, "test-job")

        assert "doesn't match" in str(exc_info.value)

    def test_video_too_short_fails(self) -> None:
        """Test that video under 3 minutes fails."""
        data = create_valid_timeline_data(num_segments=3, segment_duration=30.0)

        with pytest.raises(TimelineEvalError) as exc_info:
            evaluate_timeline(data, "test-job")

        assert "Video too short" in str(exc_info.value)

    def test_video_too_long_fails(self) -> None:
        """Test that video over 15 minutes fails."""
        # 10 segments × 100s = 1000s (> 900s max)
        data = create_valid_timeline_data(num_segments=10, segment_duration=100.0)

        with pytest.raises(TimelineEvalError) as exc_info:
            evaluate_timeline(data, "test-job")

        assert "Video too long" in str(exc_info.value)


class TestEvalResult:
    """Tests for EvalResult dataclass."""

    def test_valid_result_is_truthy(self) -> None:
        """Test that valid result evaluates to True."""
        result = EvalResult(valid=True, errors=[], warnings=[])
        assert bool(result) is True

    def test_invalid_result_is_falsy(self) -> None:
        """Test that invalid result evaluates to False."""
        result = EvalResult(valid=False, errors=["Some error"], warnings=[])
        assert bool(result) is False

    def test_result_stores_errors(self) -> None:
        """Test that result stores errors correctly."""
        errors = ["Error 1", "Error 2"]
        result = EvalResult(valid=False, errors=errors, warnings=[])
        assert result.errors == errors

    def test_result_stores_warnings(self) -> None:
        """Test that result stores warnings correctly."""
        warnings = ["Warning 1", "Warning 2"]
        result = EvalResult(valid=True, errors=[], warnings=warnings)
        assert result.warnings == warnings


class TestTimelineEvalError:
    """Tests for TimelineEvalError exception."""

    def test_error_stores_errors_list(self) -> None:
        """Test that error stores list of validation errors."""
        errors = ["Error 1", "Error 2"]
        exc = TimelineEvalError(errors)

        assert exc.errors == errors
        assert "Error 1" in str(exc)
        assert "Error 2" in str(exc)
