# FastAPI React Migration Design

## Goal

Migrate the current single-file Streamlit text-to-speech app into a two-service local development application with a FastAPI backend and a Vite React frontend. The migrated app keeps the existing product behavior: language selection, text input, optional Ollama summarization, Kokoro WAV generation, and browser audio playback.

## Current State

The app currently lives in `main.py` and combines UI, summarization, audio generation, and generated file handling in one Streamlit script. It uses:

- Kokoro `KPipeline` for text-to-speech generation.
- LangChain and Ollama with `deepseek-r1:8b` for optional summarization.
- NumPy and SoundFile to concatenate generated audio chunks and write `audio.wav`.
- The generated `audios/` directory for the final WAV file.

The migration removes Streamlit from the app and dependency set once the FastAPI and React path is in place.

## Architecture

The app will run as two development services:

- FastAPI backend on port `8000`.
- Vite React frontend on its own development port.

The backend owns all Python behavior: supported languages, text cleaning, optional summarization, Kokoro pipeline execution, WAV file writing, and audio serving. The frontend owns the interactive browser UI and calls backend endpoints under `/api`.

The frontend will use either `VITE_API_BASE_URL` or a Vite development proxy so API calls can reach the backend cleanly during local development.

## Backend Design

Backend files:

- `app/main.py`: create the FastAPI application, configure CORS for the Vite dev server, include routes, and serve generated audio files.
- `app/models.py`: define request and response schemas.
- `app/languages.py`: expose the current supported language labels and Kokoro language codes.
- `app/text.py`: implement `clean_text()` and `summarize_text()`.
- `app/audio.py`: implement audio file cleanup, Kokoro generation, WAV writing, and the injectable generation boundary used by tests.

API endpoints:

- `GET /api/health`: returns backend status.
- `GET /api/languages`: returns supported language labels and codes for the React select input.
- `POST /api/audio`: accepts text, language code, and summarize flag; returns the generated audio URL and the summarized text when summarization is enabled.
- `GET /audios/{filename}`: serves generated WAV files from the ignored `audios/` directory.

`POST /api/audio` request shape:

```json
{
  "text": "Text to generate",
  "language_code": "a",
  "summarize": false
}
```

`POST /api/audio` success shape:

```json
{
  "audio_url": "/audios/audio.wav",
  "summarized_text": null
}
```

Backend behavior:

- Blank text is rejected with validation feedback.
- Unsupported language codes are rejected with validation feedback.
- When summarization is enabled, the backend summarizes first and passes the cleaned summary to Kokoro.
- The generated audio file behavior remains intentionally simple: remove existing generated files in `audios/`, write a new `audio.wav`, and return its URL.
- TTS and Ollama failures return a concise server error message without exposing a traceback to the frontend.

## Frontend Design

Frontend files:

- `frontend/src/main.tsx`: React entry point.
- `frontend/src/App.tsx`: single-screen app composition.
- `frontend/src/api.ts`: typed API calls to FastAPI.
- `frontend/src/types.ts`: shared frontend API/domain types.
- `frontend/src/App.css`: styling for the text-to-speech tool UI.

UI behavior:

- Load languages from `GET /api/languages` on startup.
- Default to American English when available.
- Provide a language select, text area, summarize checkbox, and generate button.
- Disable generation while a request is running or text is blank.
- Show a compact error message for backend or network failures.
- After generation succeeds, render a browser audio player using the returned `audio_url`.
- When summarization is enabled and the backend returns `summarized_text`, show the final text used for generation in a readable panel.

The first screen is the usable app, not a landing page.

## Testing Strategy

Backend testing will use `pytest` and FastAPI's test client.

Backend coverage:

- `GET /api/health` returns a successful status.
- `GET /api/languages` returns the expected language list.
- `clean_text()` removes Ollama `<think>...</think>` blocks and trims whitespace.
- `POST /api/audio` rejects blank text.
- `POST /api/audio` rejects unsupported language codes.
- `POST /api/audio` returns an audio URL when the generation boundary is patched.

Frontend testing will use Vitest and React Testing Library.

Frontend coverage:

- The app loads and displays languages returned by the API.
- The generate button is disabled for blank text and while submitting.
- A successful generation response displays the audio player.
- A summarized response displays the final generated text.
- A failed API call displays an error message.

Heavy runtime dependencies are mocked or injected in tests so automated tests do not require Kokoro model work or a running Ollama service.

## Dependencies

Python dependencies:

- Add `fastapi`.
- Keep `uvicorn` as a direct backend runtime dependency.
- Add `pytest` and `httpx` for backend tests with FastAPI's `TestClient`.
- Remove `streamlit`.
- Keep Kokoro, LangChain/Ollama, NumPy, and SoundFile for existing app behavior.

Frontend dependencies:

- Add Vite, React, React DOM, TypeScript, Vitest, React Testing Library, and related development dependencies in `frontend/package.json`.

## Development Commands

Backend development:

```bash
uv run uvicorn app.main:app --reload --port 8000
```

Frontend development:

```bash
cd frontend
npm install
npm run dev
```

Backend tests:

```bash
uv run pytest
```

Frontend tests:

```bash
cd frontend
npm test
```

## Migration Notes

- `main.py` will stop being the Streamlit app entry point. The reusable logic moves into the backend package.
- The generated `audios/` directory remains ignored by git.
- `README.md` will document running the two dev services and the expected local ports.
- The implementation should keep changes focused on the migration and avoid unrelated refactors.
