import React from 'react';
import { Composition } from 'remotion';
import { TeacherTrainingVideo } from './Composition';
import { VideoCompositionProps, DEFAULT_STYLE } from './types';

// Default props for preview
const defaultProps: VideoCompositionProps = {
  title: 'Teacher Training Preview',
  segments: [
    {
      segment_id: 'seg_001',
      start_time_seconds: 0,
      duration_seconds: 5,
      slide: {
        title: 'Welcome to Teacher Training',
        bullets: ['Learn effective teaching strategies', 'Understand your students'],
        visual_prompt: 'Educational classroom scene',
      },
      narration_text: 'Welcome to this teacher training session.',
    },
  ],
  style: DEFAULT_STYLE,
};

export const RemotionRoot: React.FC = () => {
  const fps = 30;
  const durationInFrames = defaultProps.segments.reduce(
    (total, seg) => total + Math.round(seg.duration_seconds * fps),
    0
  );

  return (
    <Composition
      id="TeacherTrainingVideo"
      component={TeacherTrainingVideo}
      durationInFrames={durationInFrames}
      fps={fps}
      width={1920}
      height={1080}
      defaultProps={defaultProps}
    />
  );
};
