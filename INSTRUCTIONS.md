
# AI assisted teacher app

We're building an MVP to an app that will take school curriculum chapters in PDF form as input and return a 5-10 min video that will train teachers in how to teach that topic using pedagogical science suited to the age-group as well as real world examples that are not part of the PDF content but will make learning easier for students. We'll scale it up later to add more features, and queueing and better database structure. Currently we are building an MVP

# Technical requirements
	1.	The system must be asynchronous by default: video generation runs as a background job, the API immediately returns a job/video ID, and clients poll for status; no long-running request blocking.
	2.	The Gemini-generated timeline JSON is immutable and authoritative: all downstream steps (audio generation and Remotion rendering) must strictly follow it; if timing or constraints fail, the job must fail and be regenerated rather than auto-adjusted.
	3.	Content generation must use gemini-3-flash-preview, and slide image generation must use gemini-2.5-flash-image, with prompts optimized for clean, minimalist, pedagogy-first slides (no photorealism or decorative art).
	4.	Video rendering must be done exclusively with Remotion, consuming only the timeline JSON and generated audio/assets; the backend may orchestrate but must not render video frames itself.
	5.	The architecture must be modular and future-proof, making it straightforward to add user accounts, cloud storage, additional content types, and horizontal scaling without rewriting core orchestration logic.
    6.	Backend & orchestration: Python-based backend focused on orchestration and state management; long-running work must execute asynchronous background jobs (simple task queue for MVP), with each step idempotent and restartable.
	7.	AI & rendering (fixed): Content and timeline generation must use Gemini 3 Flash; slide image generation must use gemini-2.5-flash-image; video rendering must be done only via Remotion (Node.js/React) consuming immutable timeline JSON + audio/assets. The backend must never render frames.
	8.	Persistence: Use a relational database suitable for async jobs and retries (SQLite acceptable for MVP, but design to migrate to Postgres without refactor). Persist job/video state, errors, and artifact references.
	9.	Storage: Start with direct local filesystem storage behind a storage interface; design so it can be swapped later for managed storage (e.g., Supabase/S3) without changing business logic.
	10.	Architecture & ops bias: Clean service-layer architecture with isolated external API clients, explicit data contracts, minimal internal dashboard for operations, and a managed-services-first bias (less ops, more cost). Avoid serverless-only constraints; target VM/container-based deployment compatible with Remotion rendering.


# Version Roadmap
MVP (prove the pipeline works)

Will do
	•	Async job-based backend (submit → poll status)
	•	Upload PDF → generate one narrator teacher-training MP4
	•	Gemini 3 Flash → immutable timeline JSON
	•	gemini-2.5-flash-image → slide images
	•	Remotion → final MP4 render
	•	Persist:
	•	job status
	•	timeline JSON
	•	audio
	•	MP4
	•	Minimal internal dashboard:
	•	list jobs
	•	view status
	•	download outputs
	•	Basic retry + clear failure states

Will NOT do
	•	User authentication or accounts
	•	Student-facing content
	•	Personalization or branching
	•	Cloud storage
	•	Advanced analytics
	•	UI polish
	•	Multi-language support

⸻

V1 (make it usable and robust)

Will do
	•	Postgres instead of SQLite
	•	Proper task queue (still simple, but reliable)
	•	Storage abstraction fully enforced
	•	Better observability (logs per step, failure reason surfaced)
	•	Regeneration/versioning (re-run same PDF with new settings)
	•	Improved slide styling consistency
	•	Basic operational controls (retry job, cancel job)

Will NOT do
	•	Marketplace features
	•	Real-time rendering
	•	Fine-grained access control
	•	Heavy frontend investment
	•	Fully serverless deployment

⸻

V2 (scale + productize)

Will do
	•	User accounts and multi-tenant support
	•	Managed storage (Supabase/S3)
	•	Workflow-style orchestration (step-level retries, resume)
	•	Multiple content types:
	•	student explainer videos
	•	quiz-linked videos
	•	Horizontal scaling of Remotion renders
	•	Cost controls and quotas
	•	API-first access for integrations

Will NOT do
	•	Custom video editor
	•	Fully custom rendering engine
	•	Social/community features
	•	Content moderation at scale (unless required)
	•	Over-optimization before usage data

⸻

One guiding rule (important)

If a feature does not:
	•	reduce failure rate,
	•	reduce regeneration cost,
	•	or improve pedagogical quality,

it does not belong before V2.

