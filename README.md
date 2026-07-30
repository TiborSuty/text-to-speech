# AI Podcaster

AI Podcaster turns text into generated speech with Kokoro. It supports language-compatible voice selection and can optionally summarize the input text with a local Ollama model before generating audio.

Podcast Director adds a durable LangGraph studio workflow. It extracts source facts, drafts a schema-validated narration, interview, or explainer, checks the script against the source, and makes at most two automatic corrections. LangGraph then pauses at a persisted human-review interrupt. The approved title and host/guest turns remain editable before the existing queue and Kokoro renderer create one continuous audio file.

## Requirements

- Python 3.14
- uv
- Node.js and npm
- Ollama running locally with the `deepseek-r1:8b` model when summarization is enabled
- Docker Compose for the persistent MinIO development stack

## Backend

Install and run the FastAPI backend:

```bash
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Backend health check:

```bash
curl http://127.0.0.1:8000/api/health
```

Start a source-grounded Podcast Director workflow:

```bash
curl -X POST http://127.0.0.1:8000/api/podcast-workflows \
  -H "Content-Type: application/json" \
  -d '{"text":"SQLite runs inside an application.","format":"interview","duration":"short"}'
```

The response includes a `workflow_id`, editable `script`, extracted `facts`, remaining `issues`, and `revision_count`. Submit the reviewed script and final voices to resume the persisted interrupt:

```bash
curl -X POST http://127.0.0.1:8000/api/podcast-workflows/WORKFLOW_ID/approve \
  -H "Content-Type: application/json" \
  -d '{"script":{"title":"Inside SQLite","segments":[{"speaker":"host","text":"Where does SQLite run?"},{"speaker":"guest","text":"Inside the application process."}]},"language_code":"a","host_voice":"af_heart","guest_voice":"af_bella","audio_format":"mp3"}'
```

Approval returns a normal `job_id`, which uses the workflow ID as an idempotency key. Repeating approval recovers the same audio job instead of duplicating it. `GET /api/podcast-workflows/{workflow_id}` recovers the latest workflow checkpoint after a client or server restart.

Supported formats are `narration`, `interview`, and `explainer`. Supported duration targets are `short`, `medium`, and `long`. Ollama is required for fact extraction, drafting, evaluation, and revision. Narration drafts use one host role; interview and explainer drafts can alternate between host and guest.

Async audio generation uses a job endpoint plus Server-Sent Events:

```bash
curl -X POST http://127.0.0.1:8000/api/audio-jobs \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello world","language_code":"a","voice":"af_heart","summarize":false,"audio_format":"mp3"}'
```

Supported audio formats are `wav`, `mp3`, `flac`, and `ogg`. The `audio_format` field defaults to `wav` when omitted, preserving compatibility with existing API clients. The response contains a `job_id`. The frontend then listens to:

```text
/api/audio-jobs/{job_id}/events
```

The SSE stream sends queue, lifecycle, and generation-progress updates until the job is `cancelled`, `done`, or `failed`.

Podcast jobs use the same endpoint and may include a `segments` array. Each segment contains `speaker`, editable `text`, and a language-compatible `voice`. The worker reuses one Kokoro language pipeline, renders the turns in order, inserts a short pause between speakers, and reports continuous whole-episode progress.

Recent jobs can be listed, downloaded, or deleted:

```text
GET /api/audio-jobs?limit=20
GET /api/audio-jobs/{job_id}/download
POST /api/audio-jobs/{job_id}/cancel
DELETE /api/audio-jobs/{job_id}
```

Job metadata is persisted in SQLite at `data/audio_jobs.db` by default. Completed jobs store an object key rather than a filesystem or MinIO URL, so storage can change without migrating job records. Active jobs left by an interrupted backend process are marked failed on the next startup.

Async generation runs through a bounded FIFO worker queue. Waiting jobs include a one-based `queue_position` in API and SSE responses. Set `AUDIO_WORKER_COUNT` to control concurrency; it defaults to `1` and is clamped between `1` and `8` to keep model memory bounded.

Kokoro output is written incrementally to a hidden job-specific audio file rather than accumulated in memory. Each completed model chunk persists a monotonic `progress` percentage and sends it through SSE; `100` is reserved for audio that has been published successfully to object storage.

Cancellation is immediate for queued work. Running summarization remains blocking, so cancellation during that stage takes effect when Ollama returns. During Kokoro generation, cancellation is checked between chunks, the hidden partial audio file is deleted, and no filesystem or MinIO object is published.

Text input defaults to a maximum of 50,000 characters. Set `AUDIO_MAX_TEXT_CHARACTERS` to a value from 1 through 1,000,000. The frontend reads the effective limit from `GET /api/config`, displays a character counter, and prevents input beyond it.

Direct backend development uses filesystem object storage under `audios/` by default. Set `AUDIO_STORAGE_BACKEND=minio` and the MinIO variables listed below to use a standalone MinIO server. The Docker Compose stack configures MinIO automatically.

Terminal metadata and application-managed objects are retained for seven days by default. Set `AUDIO_RETENTION_HOURS` to another number of hours, or `0` to disable application cleanup. Compose also installs a MinIO lifecycle rule controlled by `MINIO_RETENTION_DAYS`, which defaults to seven days and acts as orphan cleanup.

## Frontend

Install and run the Vite React frontend in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL printed by the dev server. The frontend proxies `/api` requests to `http://127.0.0.1:8000`.

Choose **Podcast Director** to select a format, target length, host voice, and guest voice. Generate the workflow first, inspect its source-check result and extracted facts, edit the title or individual turns, and then select **Approve & generate podcast**. Approval resumes LangGraph and hands the episode to the normal asynchronous job and SSE flow.

## Docker Compose

Run the backend, frontend, and Ollama together:

```bash
docker compose up --build
```

Stop any existing local backend/frontend servers first if ports `8000` or `5173` are already in use.

Open:

```text
http://127.0.0.1:5173
```

The Compose stack includes:

- `ollama` on `http://127.0.0.1:11434`
- `ollama-pull`, a one-shot setup service that pulls `deepseek-r1:8b`
- `minio` S3 API on `http://127.0.0.1:9000`
- `minio` administration console on `http://127.0.0.1:9001`
- `minio-init`, a one-shot setup service that creates the private bucket and lifecycle rule
- `backend` on `http://127.0.0.1:8000`
- `frontend` on `http://127.0.0.1:5173`

The first run can take a while because Docker must build the app images and Ollama must download the model. Downloaded Ollama models and MinIO objects use named Docker volumes. SQLite job metadata and LangGraph checkpoints are persisted in `./data`.

The default MinIO credentials are intended only for local development:

```text
username: minioadmin
password: minioadmin
```

Override `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` before exposing the stack outside the local machine.

Use a different Ollama model by setting `OLLAMA_MODEL`:

```bash
OLLAMA_MODEL=llama3.1:8b docker compose up --build
```

## Tests

Run backend tests:

```bash
uv run pytest
```

Run frontend tests:

```bash
cd frontend
npm test
```

## Generated Audio

Kokoro writes each WAV atomically to a unique staging file. With filesystem storage, that file remains under `audios/`. With MinIO storage, the backend uploads it to the private `audio` bucket and removes the container-local staging file.

Playback uses a stable `/api/audio-files/{object_key}` route. Filesystem objects are served directly; private MinIO objects receive a 15-minute presigned redirect. Downloads use the same storage path with an attachment disposition.

SQLite stores:

- job status and request metadata
- LangGraph source facts, drafts, evaluations, revisions, and approval interrupts
- creation and update timestamps
- text preview and optional summary
- failure details
- the portable WAV object key

Storage configuration:

| Variable | Default | Purpose |
| --- | --- | --- |
| `AUDIO_JOBS_DB_PATH` | `data/audio_jobs.db` | SQLite metadata database |
| `PODCAST_WORKFLOW_DB_PATH` | `data/podcast_workflows.db` | LangGraph checkpoint database |
| `AUDIO_STORAGE_BACKEND` | `filesystem` | `filesystem` or `minio` |
| `AUDIO_RETENTION_HOURS` | `168` | Application metadata and object retention |
| `AUDIO_WORKER_COUNT` | `1` | Concurrent FIFO generation workers, from 1 to 8 |
| `AUDIO_MAX_TEXT_CHARACTERS` | `50000` | Maximum text length per request, clamped from 1 to 1,000,000 |
| `MINIO_ENDPOINT` | `127.0.0.1:9000` | Backend-facing MinIO endpoint |
| `MINIO_PUBLIC_ENDPOINT` | internal endpoint | Browser-facing host used to sign URLs |
| `MINIO_ACCESS_KEY` | `minioadmin` | MinIO application access key |
| `MINIO_SECRET_KEY` | `minioadmin` | MinIO application secret |
| `MINIO_BUCKET` | `audio` | Private WAV bucket |
| `MINIO_REGION` | `us-east-1` | Region used for S3 signatures |
| `MINIO_SECURE` | `false` | Enables HTTPS for the internal endpoint |
| `MINIO_RETENTION_DAYS` | `7` | Compose-managed bucket lifecycle expiry |
