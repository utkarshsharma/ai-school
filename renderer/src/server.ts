import express, { Request, Response } from 'express';
import { renderVideo } from './render/renderVideo';
import { RenderRequest, RenderResponse } from './remotion/types';

const app = express();
app.use(express.json({ limit: '50mb' }));

// Health check
app.get('/health', (_req: Request, res: Response) => {
  res.json({ status: 'healthy', service: 'ai-school-renderer' });
});

// Render endpoint
app.post('/render', async (req: Request, res: Response) => {
  const request = req.body as RenderRequest;

  if (!request.job_id || !request.output_path || !request.segments) {
    const response: RenderResponse = {
      success: false,
      error: 'Missing required fields: job_id, output_path, segments',
    };
    return res.status(400).json(response);
  }

  console.log(`[${request.job_id}] Received render request`);

  try {
    const result = await renderVideo(request);

    const response: RenderResponse = {
      success: true,
      output_path: result.outputPath,
      duration_seconds: result.durationSeconds,
    };

    return res.json(response);
  } catch (error) {
    console.error(`[${request.job_id}] Render error:`, error);

    const response: RenderResponse = {
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error',
    };

    return res.status(500).json(response);
  }
});

export { app };
