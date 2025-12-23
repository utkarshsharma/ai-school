"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import get_settings
from src.models import init_db
from src.api.routes import router as api_router, API_VERSION
from src.worker.processor import start_worker
from src.queue.job_queue import get_job_queue


class VersionHeaderMiddleware(BaseHTTPMiddleware):
    """Add API version header to all responses."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-API-Version"] = API_VERSION
        return response


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

# Add version header to all responses
app.add_middleware(VersionHeaderMiddleware)

# Include API routes
app.include_router(api_router)

# Serve storage files via HTTP (needed for Remotion to access audio/images)
# Using route-based serving instead of StaticFiles so CORS middleware applies
@app.get("/storage/{file_path:path}")
@app.head("/storage/{file_path:path}")
async def serve_storage_file(file_path: str):
    """Serve files from storage with proper CORS headers."""
    settings = get_settings()
    full_path = settings.storage_base_path / file_path
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    if not full_path.is_file():
        raise HTTPException(status_code=400, detail="Not a file")
    # Determine media type
    suffix = full_path.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".mp3": "audio/mpeg",
        ".mp4": "video/mp4",
        ".json": "application/json",
    }
    media_type = media_types.get(suffix, "application/octet-stream")
    return FileResponse(full_path, media_type=media_type)


@app.get("/health")
async def health_check():
    """Health check endpoint with queue status."""
    queue = get_job_queue()
    queue_status = queue.health_check()
    return {
        "status": "healthy",
        "service": "ai-school-backend",
        "queue": queue_status,
    }


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Internal dashboard for operations."""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI School - Dashboard</title>
    <style>
        :root {
            --primary: #5c6bc0;
            --primary-dark: #3f51b5;
            --primary-light: #c5cae9;
            --success: #66bb6a;
            --success-bg: #e8f5e9;
            --warning: #ffa726;
            --warning-bg: #fff3e0;
            --error: #ef5350;
            --error-bg: #ffebee;
            --info: #42a5f5;
            --info-bg: #e3f2fd;
            --gray-50: #fafafa;
            --gray-100: #f5f5f5;
            --gray-200: #eeeeee;
            --gray-300: #e0e0e0;
            --gray-500: #9e9e9e;
            --gray-700: #616161;
            --gray-900: #212121;
            --radius: 12px;
            --shadow: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06);
            --shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.1), 0 4px 6px -2px rgba(0,0,0,0.05);
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Inter', system-ui, -apple-system, sans-serif;
            background: linear-gradient(135deg, var(--gray-100) 0%, var(--gray-200) 100%);
            min-height: 100vh;
            padding: 24px;
            color: var(--gray-900);
        }
        .container { max-width: 1280px; margin: 0 auto; }
        .header {
            display: flex;
            align-items: center;
            gap: 16px;
            margin-bottom: 32px;
        }
        .logo {
            width: 48px;
            height: 48px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            border-radius: var(--radius);
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 24px;
            font-weight: 700;
        }
        h1 {
            color: var(--gray-900);
            font-size: 28px;
            font-weight: 700;
            letter-spacing: -0.5px;
        }
        h1 span { color: var(--primary); }
        .subtitle { color: var(--gray-500); font-size: 14px; margin-top: 2px; }
        .card {
            background: white;
            border-radius: var(--radius);
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: var(--shadow);
            border: 1px solid var(--gray-200);
        }
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        .card-title {
            font-size: 18px;
            font-weight: 600;
            color: var(--gray-900);
        }
        .upload-area {
            border: 2px dashed var(--gray-300);
            padding: 48px 24px;
            text-align: center;
            border-radius: var(--radius);
            cursor: pointer;
            transition: all 0.2s ease;
            background: var(--gray-50);
        }
        .upload-area:hover {
            border-color: var(--primary);
            background: var(--primary-light);
        }
        .upload-area.dragover {
            border-color: var(--primary);
            background: var(--primary-light);
            transform: scale(1.01);
        }
        .upload-icon {
            width: 64px;
            height: 64px;
            margin: 0 auto 16px;
            background: var(--primary-light);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 28px;
        }
        .upload-text { color: var(--gray-700); font-size: 16px; font-weight: 500; }
        .upload-hint { color: var(--gray-500); font-size: 13px; margin-top: 8px; }
        input[type="file"] { display: none; }
        .btn {
            background: var(--primary);
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.2s ease;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }
        .btn:hover { background: var(--primary-dark); transform: translateY(-1px); }
        .btn:active { transform: translateY(0); }
        .btn-sm { padding: 6px 12px; font-size: 12px; border-radius: 6px; }
        .btn-success { background: var(--success); }
        .btn-success:hover { background: #4caf50; }
        .btn-secondary { background: var(--gray-500); }
        .btn-secondary:hover { background: var(--gray-700); }
        .btn-danger { background: var(--error); }
        .btn-danger:hover { background: #d32f2f; }
        .btn-outline {
            background: transparent;
            border: 1px solid var(--gray-300);
            color: var(--gray-700);
        }
        .btn-outline:hover { background: var(--gray-100); border-color: var(--gray-500); }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 14px 16px; text-align: left; }
        th {
            background: var(--gray-50);
            font-weight: 600;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--gray-500);
            border-bottom: 2px solid var(--gray-200);
        }
        td { border-bottom: 1px solid var(--gray-100); vertical-align: middle; }
        tr:hover td { background: var(--gray-50); }
        .filename {
            font-weight: 500;
            color: var(--gray-900);
            max-width: 200px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .badge {
            padding: 5px 10px;
            border-radius: 20px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.3px;
        }
        .badge-pending { background: var(--warning-bg); color: #e65100; }
        .badge-processing { background: var(--info-bg); color: #1565c0; }
        .badge-completed { background: var(--success-bg); color: #2e7d32; }
        .badge-failed { background: var(--error-bg); color: #c62828; }
        .badge-cancelled { background: var(--gray-200); color: var(--gray-700); }
        .progress-container { display: flex; align-items: center; gap: 10px; }
        .progress-stage {
            font-size: 11px;
            font-weight: 500;
            color: var(--primary);
            text-transform: uppercase;
            min-width: 60px;
        }
        .progress-bar {
            flex: 1;
            height: 6px;
            background: var(--gray-200);
            border-radius: 3px;
            overflow: hidden;
            min-width: 80px;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, var(--primary) 0%, var(--primary-dark) 100%);
            border-radius: 3px;
            transition: width 0.3s ease;
        }
        .progress-pct { font-size: 12px; color: var(--gray-500); font-weight: 500; min-width: 36px; }
        .timing-badges { display: flex; flex-wrap: wrap; gap: 4px; }
        .timing-badge {
            font-size: 10px;
            padding: 3px 6px;
            background: var(--gray-100);
            border-radius: 4px;
            color: var(--gray-700);
        }
        .timing-badge strong { color: var(--gray-900); }
        .error-text {
            color: var(--error);
            font-size: 12px;
            max-width: 200px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            cursor: help;
        }
        .actions { display: flex; gap: 6px; flex-wrap: wrap; }
        .meta { color: var(--gray-500); font-size: 13px; }
        .duration { font-weight: 500; color: var(--gray-700); }
        #message {
            padding: 14px 18px;
            margin-bottom: 20px;
            border-radius: 8px;
            display: none;
            font-weight: 500;
            font-size: 14px;
        }
        #message.success { background: var(--success-bg); color: #2e7d32; display: flex; align-items: center; gap: 10px; }
        #message.error { background: var(--error-bg); color: #c62828; display: flex; align-items: center; gap: 10px; }
        .empty-state {
            text-align: center;
            padding: 48px 24px;
            color: var(--gray-500);
        }
        .empty-state-icon { font-size: 48px; margin-bottom: 16px; opacity: 0.5; }
        .modal-overlay {
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,0.5);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 1000;
        }
        .modal-overlay.active { display: flex; }
        .modal {
            background: white;
            border-radius: var(--radius);
            padding: 24px;
            max-width: 600px;
            width: 90%;
            max-height: 80vh;
            overflow-y: auto;
            box-shadow: var(--shadow-lg);
        }
        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        .modal-title { font-size: 18px; font-weight: 600; }
        .modal-close {
            background: none;
            border: none;
            font-size: 24px;
            cursor: pointer;
            color: var(--gray-500);
        }
        .log-section { margin-bottom: 16px; }
        .log-label { font-size: 11px; text-transform: uppercase; color: var(--gray-500); margin-bottom: 4px; }
        .log-value { font-family: 'SF Mono', monospace; font-size: 13px; color: var(--gray-900); }
        .log-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
        @media (max-width: 768px) {
            .log-grid { grid-template-columns: 1fr; }
            .actions { flex-direction: column; }
            th, td { padding: 10px 8px; font-size: 13px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">A</div>
            <div>
                <h1>AI <span>School</span></h1>
                <div class="subtitle">Teacher Training Video Generator</div>
            </div>
        </div>

        <div id="message"></div>

        <div class="card">
            <div class="card-header">
                <span class="card-title">Upload Curriculum PDF</span>
            </div>
            <div class="upload-area" id="uploadArea">
                <div class="upload-icon">&#128196;</div>
                <div class="upload-text">Drag & drop a PDF file here, or click to select</div>
                <div class="upload-hint">Maximum file size: 50MB</div>
                <input type="file" id="fileInput" accept=".pdf">
            </div>
        </div>

        <div class="card">
            <div class="card-header">
                <span class="card-title">Processing Jobs</span>
                <button class="btn btn-outline" onclick="loadJobs()">&#8635; Refresh</button>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>File</th>
                        <th>Status</th>
                        <th>Progress / Timing</th>
                        <th>Duration</th>
                        <th>Created</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody id="jobsTable">
                    <tr><td colspan="6"><div class="empty-state"><div class="empty-state-icon">&#128269;</div>Loading jobs...</div></td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <div class="modal-overlay" id="logModal">
        <div class="modal">
            <div class="modal-header">
                <span class="modal-title">Job Details</span>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <div id="logContent"></div>
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
            showMessage('&#8987; Uploading ' + file.name + '...', 'success');
            const formData = new FormData();
            formData.append('file', file);
            try {
                const res = await fetch('/api/jobs', { method: 'POST', body: formData });
                if (!res.ok) throw new Error((await res.json()).detail || 'Upload failed');
                showMessage('&#10003; Job created! Video generation started.', 'success');
                loadJobs();
            } catch (e) {
                showMessage('&#10007; ' + e.message, 'error');
            }
        }

        async function loadJobs() {
            try {
                const res = await fetch('/api/jobs');
                const data = await res.json();
                const tbody = document.getElementById('jobsTable');
                if (data.jobs.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="6"><div class="empty-state"><div class="empty-state-icon">&#128218;</div>No jobs yet. Upload a PDF to get started.</div></td></tr>';
                    return;
                }
                tbody.innerHTML = data.jobs.map(job => {
                    const timings = Object.entries(job.stage_durations || {});
                    return `
                    <tr>
                        <td><div class="filename" title="${job.original_filename}">${job.original_filename}</div></td>
                        <td><span class="badge badge-${job.status}">${job.status}</span></td>
                        <td>
                            ${job.status === 'processing' ? `
                                <div class="progress-container">
                                    <span class="progress-stage">${job.current_stage || '...'}</span>
                                    <div class="progress-bar"><div class="progress-fill" style="width: ${job.stage_progress}%"></div></div>
                                    <span class="progress-pct">${job.stage_progress}%</span>
                                </div>
                            ` : job.status === 'completed' && timings.length > 0 ? `
                                <div class="timing-badges">
                                    ${timings.map(([stage, dur]) => `<span class="timing-badge"><strong>${stage}</strong> ${dur.toFixed(1)}s</span>`).join('')}
                                </div>
                            ` : job.error_message ? `
                                <div class="error-text" title="${job.error_message}">
                                    ${job.error_stage ? '[' + job.error_stage + '] ' : ''}${job.error_message.substring(0, 50)}${job.error_message.length > 50 ? '...' : ''}
                                </div>
                            ` : '<span class="meta">-</span>'}
                        </td>
                        <td>${job.video_duration_seconds ? `<span class="duration">${(job.video_duration_seconds / 60).toFixed(1)} min</span>` : '<span class="meta">-</span>'}</td>
                        <td><span class="meta">${new Date(job.created_at).toLocaleString()}</span></td>
                        <td class="actions">
                            ${job.status === 'completed' ? `<button class="btn btn-sm btn-success" onclick="downloadVideo('${job.id}')">&#8595; Download</button>` : ''}
                            ${job.status === 'failed' ? `<button class="btn btn-sm" onclick="retryJob('${job.id}')">&#8635; Retry</button>` : ''}
                            ${(job.status === 'pending' || job.status === 'processing') ? `<button class="btn btn-sm btn-danger" onclick="cancelJob('${job.id}')">&#10005; Cancel</button>` : ''}
                            <button class="btn btn-sm btn-secondary" onclick="viewLogs('${job.id}')">&#128196; Logs</button>
                            <button class="btn btn-sm btn-outline" onclick="deleteJob('${job.id}')">&#128465;</button>
                        </td>
                    </tr>
                `}).join('');
            } catch (e) {
                console.error(e);
            }
        }

        function downloadVideo(jobId) {
            window.location.href = `/api/jobs/${jobId}/video`;
        }

        async function retryJob(jobId) {
            try {
                await fetch(`/api/jobs/${jobId}/retry`, { method: 'POST' });
                showMessage('&#10003; Job requeued for processing', 'success');
                loadJobs();
            } catch (e) {
                showMessage('&#10007; ' + e.message, 'error');
            }
        }

        async function cancelJob(jobId) {
            if (!confirm('Cancel this job? It will stop at the next stage boundary.')) return;
            try {
                const res = await fetch(`/api/jobs/${jobId}/cancel`, { method: 'POST' });
                if (!res.ok) throw new Error((await res.json()).detail || 'Cancel failed');
                showMessage('&#10003; Cancellation requested', 'success');
                loadJobs();
            } catch (e) {
                showMessage('&#10007; ' + e.message, 'error');
            }
        }

        async function deleteJob(jobId) {
            if (!confirm('Delete this job and all its files?')) return;
            try {
                await fetch(`/api/jobs/${jobId}?hard_delete=true`, { method: 'DELETE' });
                loadJobs();
            } catch (e) {
                showMessage('&#10007; ' + e.message, 'error');
            }
        }

        async function viewLogs(jobId) {
            try {
                const res = await fetch(`/api/jobs/${jobId}/logs`);
                const d = await res.json();
                const durations = Object.entries(d.stage_durations || {});
                document.getElementById('logContent').innerHTML = `
                    <div class="log-grid">
                        <div class="log-section">
                            <div class="log-label">Job ID</div>
                            <div class="log-value">${d.job_id}</div>
                        </div>
                        <div class="log-section">
                            <div class="log-label">Status</div>
                            <div class="log-value"><span class="badge badge-${d.status}">${d.status}</span></div>
                        </div>
                        <div class="log-section">
                            <div class="log-label">Current Stage</div>
                            <div class="log-value">${d.current_stage || '-'}</div>
                        </div>
                        <div class="log-section">
                            <div class="log-label">Progress</div>
                            <div class="log-value">${d.stage_progress}%</div>
                        </div>
                        <div class="log-section">
                            <div class="log-label">Created</div>
                            <div class="log-value">${d.created_at ? new Date(d.created_at).toLocaleString() : '-'}</div>
                        </div>
                        <div class="log-section">
                            <div class="log-label">Completed</div>
                            <div class="log-value">${d.completed_at ? new Date(d.completed_at).toLocaleString() : '-'}</div>
                        </div>
                    </div>
                    ${durations.length > 0 ? `
                    <div class="log-section" style="margin-top: 16px;">
                        <div class="log-label">Stage Timings</div>
                        <div class="timing-badges" style="margin-top: 8px;">
                            ${durations.map(([stage, dur]) => `<span class="timing-badge"><strong>${stage}</strong> ${dur.toFixed(2)}s</span>`).join('')}
                        </div>
                    </div>
                    ` : ''}
                    ${d.error_message ? `
                    <div class="log-section" style="margin-top: 16px;">
                        <div class="log-label">Error (${d.error_stage || 'unknown stage'})</div>
                        <div class="log-value" style="color: var(--error); white-space: pre-wrap;">${d.error_message}</div>
                    </div>
                    ` : ''}
                `;
                document.getElementById('logModal').classList.add('active');
            } catch (e) {
                showMessage('&#10007; Failed to load logs', 'error');
            }
        }

        function closeModal() {
            document.getElementById('logModal').classList.remove('active');
        }

        function showMessage(text, type) {
            message.innerHTML = text;
            message.className = type;
            setTimeout(() => message.className = '', 5000);
        }

        document.getElementById('logModal').addEventListener('click', (e) => {
            if (e.target.id === 'logModal') closeModal();
        });

        loadJobs();
        setInterval(loadJobs, 5000);
    </script>
</body>
</html>
"""
