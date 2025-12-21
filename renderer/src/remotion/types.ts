/**
 * Type definitions for the video timeline.
 * These types mirror the Python Timeline schema.
 */

export interface SlideContent {
  title: string;
  bullets: string[];
  visual_prompt: string;
}

export interface TimelineSegment {
  segment_id: string;
  start_time_seconds: number;
  duration_seconds: number;
  slide: SlideContent;
  narration_text: string;
  // Added by backend after asset generation
  audio_path?: string;
  image_path?: string;
}

export interface VideoStyle {
  backgroundColor: string;
  primaryColor: string;
  accentColor: string;
  fontFamily: string;
}

export interface RenderRequest {
  job_id: string;
  output_path: string;
  fps: number;
  width: number;
  height: number;
  title: string;
  total_duration_seconds: number;
  segments: TimelineSegment[];
  style?: VideoStyle;
}

export interface RenderResponse {
  success: boolean;
  output_path?: string;
  duration_seconds?: number;
  error?: string;
}

// Props for Remotion composition
export interface VideoCompositionProps {
  title: string;
  segments: TimelineSegment[];
  style: VideoStyle;
}

// Default style
export const DEFAULT_STYLE: VideoStyle = {
  backgroundColor: '#FAFAFA',
  primaryColor: '#1A1A2E',
  accentColor: '#4A69BD',
  fontFamily: 'Inter, system-ui, sans-serif',
};
