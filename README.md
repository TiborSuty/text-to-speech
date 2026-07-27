# AI Podcaster

AI Podcaster turns text into generated speech with Kokoro. It can optionally summarize the input text with a local Ollama model before generating audio.

## Requirements

- Python 3.14
- uv
- Node.js and npm
- Ollama running locally with the `deepseek-r1:8b` model when summarization is enabled

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

Async audio generation uses a job endpoint plus Server-Sent Events:

```bash
curl -X POST http://127.0.0.1:8000/api/audio-jobs \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello world","language_code":"a","summarize":false}'
```

The response contains a `job_id`. The frontend then listens to:

```text
/api/audio-jobs/{job_id}/events
```

The SSE stream sends job status updates until the job is `done` or `failed`.

## Frontend

Install and run the Vite React frontend in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL printed by the dev server. The frontend proxies `/api` and `/audios` requests to `http://127.0.0.1:8000`.

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
- `backend` on `http://127.0.0.1:8000`
- `frontend` on `http://127.0.0.1:5173`

The first run can take a while because Docker must build the app images and Ollama must download the model. Downloaded Ollama models are persisted in the `ollama` Docker volume, and generated audio is written to `./audios`.

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

Generated WAV files are written to `audios/`. The directory is ignored by git.
