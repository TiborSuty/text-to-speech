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

## Frontend

Install and run the Vite React frontend in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL printed by the dev server. The frontend proxies `/api` and `/audios` requests to `http://127.0.0.1:8000`.

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
