import React from 'react';
import { AbsoluteFill, Audio, Sequence } from 'remotion';
import { VideoCompositionProps, DEFAULT_STYLE } from './types';
import { Slide } from './components/Slide';

export const TeacherTrainingVideo: React.FC<VideoCompositionProps> = ({
  title,
  segments,
  style = DEFAULT_STYLE,
}) => {
  // Calculate frame offsets for each segment
  const fps = 30;
  let currentFrame = 0;

  return (
    <AbsoluteFill style={{ backgroundColor: style.backgroundColor }}>
      {segments.map((segment, index) => {
        const startFrame = currentFrame;
        const durationFrames = Math.round(segment.duration_seconds * fps);
        currentFrame += durationFrames;

        return (
          <Sequence
            key={segment.segment_id}
            from={startFrame}
            durationInFrames={durationFrames}
            name={`Segment ${index + 1}: ${segment.slide.title}`}
          >
            {/* Slide visual */}
            <Slide
              content={segment.slide}
              style={style}
              imagePath={segment.image_path}
              durationFrames={durationFrames}
            />

            {/* Audio for this segment */}
            {segment.audio_path && (
              <Audio
                src={segment.audio_path}
                volume={1}
              />
            )}
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
