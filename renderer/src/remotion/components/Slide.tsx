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
      {/* Background image if available */}
      {imagePath && (
        <AbsoluteFill>
          <Img
            src={imagePath}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              opacity: 0.15,
            }}
          />
        </AbsoluteFill>
      )}

      {/* Content overlay */}
      <AbsoluteFill
        style={{
          padding: '80px 120px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
        }}
      >
        {/* Title */}
        <h1
          style={{
            fontFamily: style.fontFamily,
            fontSize: 72,
            fontWeight: 700,
            color: style.primaryColor,
            marginBottom: 48,
            lineHeight: 1.2,
          }}
        >
          {content.title}
        </h1>

        {/* Bullets */}
        <ul
          style={{
            listStyle: 'none',
            padding: 0,
            margin: 0,
          }}
        >
          {content.bullets.map((bullet, index) => {
            // Staggered animation for bullets
            const bulletDelay = 20 + index * 10;
            const bulletOpacity = interpolate(
              frame,
              [bulletDelay, bulletDelay + 15],
              [0, 1],
              { extrapolateRight: 'clamp', extrapolateLeft: 'clamp' }
            );

            return (
              <li
                key={index}
                style={{
                  fontFamily: style.fontFamily,
                  fontSize: 42,
                  color: style.primaryColor,
                  marginBottom: 24,
                  paddingLeft: 40,
                  position: 'relative',
                  opacity: bulletOpacity,
                }}
              >
                <span
                  style={{
                    position: 'absolute',
                    left: 0,
                    color: style.accentColor,
                  }}
                >
                  •
                </span>
                {bullet}
              </li>
            );
          })}
        </ul>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
