import path from 'path';
import { fileURLToPath } from 'url';
import { bundle } from '@remotion/bundler';
import { renderMedia, selectComposition } from '@remotion/renderer';
import { RenderRequest, VideoCompositionProps, DEFAULT_STYLE } from '../remotion/types';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export interface RenderResult {
  outputPath: string;
  durationSeconds: number;
}

export async function renderVideo(request: RenderRequest): Promise<RenderResult> {
  const {
    job_id,
    output_path,
    fps,
    width,
    height,
    title,
    segments,
    style = DEFAULT_STYLE,
  } = request;

  console.log(`[${job_id}] Starting render: ${segments.length} segments`);

  // Calculate total duration in frames
  const totalDurationFrames = segments.reduce(
    (total, seg) => total + Math.round(seg.duration_seconds * fps),
    0
  );

  console.log(`[${job_id}] Duration: ${totalDurationFrames} frames (${totalDurationFrames / fps}s)`);

  // Bundle the Remotion project
  const bundleLocation = await bundle({
    entryPoint: path.resolve(__dirname, '../remotion/index.ts'),
    webpackOverride: (config) => config,
  });

  console.log(`[${job_id}] Bundle created`);

  // Prepare composition props
  const inputProps: VideoCompositionProps = {
    title,
    segments,
    style,
  };

  // Select the composition
  const composition = await selectComposition({
    serveUrl: bundleLocation,
    id: 'TeacherTrainingVideo',
    inputProps,
  });

  // Override duration based on our segments
  const compositionWithDuration = {
    ...composition,
    durationInFrames: totalDurationFrames,
    fps,
    width,
    height,
  };

  console.log(`[${job_id}] Rendering video...`);

  // Render the video
  await renderMedia({
    composition: compositionWithDuration,
    serveUrl: bundleLocation,
    codec: 'h264',
    outputLocation: output_path,
    inputProps,
    onProgress: ({ progress }) => {
      const percent = Math.round(progress * 100);
      // Log every 5% progress
      if (percent % 5 === 0) {
        console.log(`[${job_id}] Render progress: ${percent}%`);
      }
    },
  });

  console.log(`[${job_id}] Render complete: ${output_path}`);

  return {
    outputPath: output_path,
    durationSeconds: totalDurationFrames / fps,
  };
}
