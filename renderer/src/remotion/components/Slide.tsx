import React from 'react';
import { AbsoluteFill, Img, interpolate, useCurrentFrame } from 'remotion';
import { SlideContent, VideoStyle } from '../types';

interface SlideProps {
  content: SlideContent;
  style: VideoStyle;
  imagePath?: string;
  durationFrames: number;
}

export const Slide: React.FC<SlideProps> = ({
  content,
  style,
  imagePath,
  durationFrames,
}) => {
  const frame = useCurrentFrame();

  // Fade in animation
  const opacity = interpolate(frame, [0, 15], [0, 1], {
    extrapolateRight: 'clamp',
  });

  // Fade out at end
  const fadeOutOpacity = interpolate(
    frame,
    [durationFrames - 15, durationFrames],
    [1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
  );

  const finalOpacity = Math.min(opacity, fadeOutOpacity);

  return (
    <AbsoluteFill
      style={{
        backgroundColor: style.backgroundColor,
        opacity: finalOpacity,
      }}
    >
      {/* Full image at 100% opacity */}
      {imagePath && (
        <AbsoluteFill>
          <Img
            src={imagePath}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
            }}
          />
        </AbsoluteFill>
      )}

      {/* Minimal title at bottom center */}
      <AbsoluteFill
        style={{
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'flex-end',
          alignItems: 'center',
          padding: '0 60px 60px 60px',
        }}
      >
        <div
          style={{
            backgroundColor: 'rgba(0, 0, 0, 0.6)',
            padding: '16px 32px',
            borderRadius: 8,
            maxWidth: '80%',
          }}
        >
          <h1
            style={{
              fontFamily: style.fontFamily,
              fontSize: 42,
              fontWeight: 600,
              color: '#ffffff',
              margin: 0,
              textAlign: 'center',
              lineHeight: 1.3,
            }}
          >
            {content.title}
          </h1>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
