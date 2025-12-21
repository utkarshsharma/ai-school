import { app } from './server';

const PORT = process.env.RENDERER_PORT || 3000;

app.listen(PORT, () => {
  console.log(`Remotion renderer listening on port ${PORT}`);
  console.log(`Health check: http://localhost:${PORT}/health`);
});
