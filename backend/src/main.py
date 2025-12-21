"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from src.config import get_settings
from src.models import init_db
from src.api.routes import router as api_router
from src.worker.processor import start_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    settings = get_settings()
    settings.storage_base_path.mkdir(parents=True, exist_ok=True)
    settings.pdf_path.mkdir(parents=True, exist_ok=True)
    settings.audio_path.mkdir(parents=True, exist_ok=True)
    settings.images_path.mkdir(parents=True, exist_ok=True)
    settings.videos_path.mkdir(parents=True, exist_ok=True)
    settings.timelines_path.mkdir(parents=True, exist_ok=True)
    init_db()
    start_worker()
    yield
    # Shutdown


app = FastAPI(
    title="AI School - Teacher Training Video Generator",
    description="Generate teacher training videos from curriculum PDFs",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "ai-school-backend"}


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Minimal internal dashboard for operations."""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI School - Dashboard</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: system-ui, -apple-system, sans-serif; background: #f5f5f5; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { color: #1a1a2e; margin-bottom: 20px; }
        .card { background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .upload-area { border: 2px dashed #ccc; padding: 40px; text-align: center; border-radius: 8px; cursor: pointer; }
        .upload-area:hover { border-color: #4a69bd; background: #f8f9ff; }
        .upload-area.dragover { border-color: #4a69bd; background: #f0f4ff; }
        input[type="file"] { display: none; }
        .btn { background: #4a69bd; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; }
        .btn:hover { background: #3a5aa8; }
        .btn:disabled { background: #ccc; cursor: not-allowed; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #eee; }
        th { background: #f8f9fa; font-weight: 600; }
        .status { padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: 500; }
        .status-pending { background: #fff3cd; color: #856404; }
        .status-processing { background: #cce5ff; color: #004085; }
        .status-completed { background: #d4edda; color: #155724; }
        .status-failed { background: #f8d7da; color: #721c24; }
        .actions button { margin-right: 8px; padding: 4px 8px; font-size: 12px; }
        .progress { display: flex; align-items: center; gap: 8px; }
        .progress-bar { flex: 1; height: 8px; background: #e9ecef; border-radius: 4px; overflow: hidden; }
        .progress-fill { height: 100%; background: #4a69bd; transition: width 0.3s; }
        #message { padding: 10px; margin-bottom: 10px; border-radius: 4px; display: none; }
        #message.success { background: #d4edda; color: #155724; display: block; }
        #message.error { background: #f8d7da; color: #721c24; display: block; }
    </style>
</head>
<body>
    <div class="container">
        <h1>AI School - Teacher Training Video Generator</h1>

        <div id="message"></div>

        <div class="card">
            <h2 style="margin-bottom: 15px;">Upload PDF</h2>
            <div class="upload-area" id="uploadArea">
                <p>Drag & drop a PDF file here, or click to select</p>
                <p style="color: #888; font-size: 14px; margin-top: 8px;">Maximum file size: 50MB</p>
                <input type="file" id="fileInput" accept=".pdf">
            </div>
        </div>

        <div class="card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                <h2>Jobs</h2>
                <button class="btn" onclick="loadJobs()">Refresh</button>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>File</th>
                        <th>Status</th>
                        <th>Progress</th>
                        <th>Duration</th>
                        <th>Created</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody id="jobsTable">
                    <tr><td colspan="6" style="text-align: center; color: #888;">Loading...</td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <script>
        const uploadArea = document.getElementById('uploadArea');
        const fileInput = document.getElementById('fileInput');
        const message = document.getElementById('message');

        uploadArea.addEventListener('click', () => fileInput.click());
        uploadArea.addEventListener('dragover', (e) => { e.preventDefault(); uploadArea.classList.add('dragover'); });
        uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('dragover'));
        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('dragover');
            const file = e.dataTransfer.files[0];
            if (file && file.name.endsWith('.pdf')) uploadFile(file);
            else showMessage('Please select a PDF file', 'error');
        });
        fileInput.addEventListener('change', () => {
            if (fileInput.files[0]) uploadFile(fileInput.files[0]);
        });

        async function uploadFile(file) {
            showMessage('Uploading...', 'success');
            const formData = new FormData();
            formData.append('file', file);
            try {
                const res = await fetch('/api/jobs', { method: 'POST', body: formData });
                if (!res.ok) throw new Error((await res.json()).detail || 'Upload failed');
                showMessage('Job created! Processing...', 'success');
                loadJobs();
            } catch (e) {
                showMessage(e.message, 'error');
            }
        }

        async function loadJobs() {
            try {
                const res = await fetch('/api/jobs');
                const data = await res.json();
                const tbody = document.getElementById('jobsTable');
                if (data.jobs.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: #888;">No jobs yet</td></tr>';
                    return;
                }
                tbody.innerHTML = data.jobs.map(job => `
                    <tr>
                        <td>${job.original_filename}</td>
                        <td><span class="status status-${job.status}">${job.status}</span></td>
                        <td>
                            ${job.status === 'processing' ? `
                                <div class="progress">
                                    <span>${job.current_stage || ''}</span>
                                    <div class="progress-bar"><div class="progress-fill" style="width: ${job.stage_progress}%"></div></div>
                                    <span>${job.stage_progress}%</span>
                                </div>
                            ` : (job.error_message ? `<span style="color: #721c24; font-size: 12px;">${job.error_message.substring(0, 50)}...</span>` : '-')}
                        </td>
                        <td>${job.video_duration_seconds ? job.video_duration_seconds.toFixed(1) + 's' : '-'}</td>
                        <td>${new Date(job.created_at).toLocaleString()}</td>
                        <td class="actions">
                            ${job.status === 'completed' ? `<button class="btn" onclick="downloadVideo('${job.id}')">Download</button>` : ''}
                            ${job.status === 'failed' ? `<button class="btn" onclick="retryJob('${job.id}')">Retry</button>` : ''}
                            <button class="btn" style="background: #dc3545;" onclick="deleteJob('${job.id}')">Delete</button>
                        </td>
                    </tr>
                `).join('');
            } catch (e) {
                console.error(e);
            }
        }

        async function downloadVideo(jobId) {
            window.location.href = `/api/jobs/${jobId}/video`;
        }

        async function retryJob(jobId) {
            try {
                await fetch(`/api/jobs/${jobId}/retry`, { method: 'POST' });
                showMessage('Job requeued', 'success');
                loadJobs();
            } catch (e) {
                showMessage(e.message, 'error');
            }
        }

        async function deleteJob(jobId) {
            if (!confirm('Delete this job?')) return;
            try {
                await fetch(`/api/jobs/${jobId}`, { method: 'DELETE' });
                loadJobs();
            } catch (e) {
                showMessage(e.message, 'error');
            }
        }

        function showMessage(text, type) {
            message.textContent = text;
            message.className = type;
            setTimeout(() => message.className = '', 5000);
        }

        loadJobs();
        setInterval(loadJobs, 5000);
    </script>
</body>
</html>
"""
