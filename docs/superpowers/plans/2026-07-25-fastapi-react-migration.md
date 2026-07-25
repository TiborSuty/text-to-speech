# FastAPI React Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current Streamlit text-to-speech app with a FastAPI backend and a Vite React frontend while preserving the current language selection, optional summarization, WAV generation, and browser playback behavior.

**Architecture:** The backend is a small FastAPI package under `app/` that owns languages, summarization, Kokoro audio generation, and static serving of generated audio. The frontend is a Vite React app under `frontend/` that renders the usable tool screen and calls backend endpoints under `/api` while running as a separate dev service.

**Tech Stack:** Python 3.14, FastAPI, Uvicorn, Pydantic, pytest, httpx, Kokoro, LangChain/Ollama, NumPy, SoundFile, Vite, React, TypeScript, Vitest, React Testing Library.

---

## File Structure

Create and modify these files:

- Create: `app/__init__.py` marks the backend package.
- Create: `app/languages.py` stores supported Kokoro language labels and codes.
- Create: `app/text.py` stores text cleanup and Ollama summarization logic.
- Create: `app/audio.py` stores generated audio cleanup and Kokoro WAV generation.
- Create: `app/models.py` stores FastAPI request and response schemas.
- Create: `app/main.py` creates the FastAPI app, CORS, routes, and generated audio serving.
- Create: `tests/test_languages.py` covers supported language behavior.
- Create: `tests/test_text.py` covers `clean_text()`.
- Create: `tests/test_api.py` covers FastAPI endpoints without running Kokoro or Ollama.
- Modify: `pyproject.toml` removes Streamlit and unused old dependencies, then adds FastAPI, direct Uvicorn, pytest, and httpx.
- Modify: `uv.lock` updates Python dependency resolution.
- Create: `frontend/` Vite React app files.
- Create: `frontend/src/types.ts` stores frontend API/domain types.
- Create: `frontend/src/api.ts` stores typed API calls.
- Create: `frontend/src/api.test.ts` covers API client behavior.
- Create: `frontend/src/App.tsx` stores the single-screen React app.
- Create: `frontend/src/App.test.tsx` covers frontend user behavior.
- Create: `frontend/src/App.css` styles the tool UI.
- Create: `frontend/src/setupTests.ts` installs jest-dom matchers for Vitest.
- Modify: `.gitignore` ignores frontend install/build output and local uv cache.
- Modify: `README.md` documents two-service local development.
- Delete: `main.py` after the FastAPI and React paths are tested.

## Task 1: Backend Dependency Setup

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `.gitignore`

- [ ] **Step 1: Update Python dependencies**

Run:

```bash
uv remove streamlit langchain-community langgraph tavily-python
uv add fastapi uvicorn
uv add --dev pytest httpx
```

Expected: `pyproject.toml` keeps the existing project metadata and direct dependencies for:

```toml
dependencies = [
    "fastapi",
    "kokoro>=0.9.4",
    "langchain-core>=1.5.1",
    "langchain-ollama>=1.1.0",
    "numpy>=2.5.1",
    "soundfile>=0.14.0",
    "uvicorn",
]
```

Expected: `pyproject.toml` also contains a dev dependency group with:

```toml
[dependency-groups]
dev = [
    "httpx",
    "pytest",
]
```

- [ ] **Step 2: Verify Streamlit is no longer a direct dependency**

Run:

```bash
rg -n '"streamlit|langchain-community|langgraph|tavily-python"' pyproject.toml
```

Expected: no matches.

- [ ] **Step 3: Add generated local directories to `.gitignore`**

Modify `.gitignore` so it contains:

```gitignore
# Python-generated files
__pycache__/
*.py[oc]
build/
dist/
wheels/
*.egg-info

# Virtual environments and local caches
.venv
.uv-cache/

# Frontend dependencies and build output
frontend/node_modules/
frontend/dist/
frontend/.vite/
frontend/coverage/

# Generated audio
audios/
```

- [ ] **Step 4: Verify backend tooling imports**

Run:

```bash
uv run python -c "import fastapi, httpx, pytest, uvicorn; print('backend deps ok')"
```

Expected: prints `backend deps ok`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock .gitignore
git commit -m "chore: add fastapi backend dependencies"
```

## Task 2: Backend Domain Modules

**Files:**
- Create: `app/__init__.py`
- Create: `app/languages.py`
- Create: `app/text.py`
- Create: `tests/test_languages.py`
- Create: `tests/test_text.py`

- [ ] **Step 1: Write failing language tests**

Create `tests/test_languages.py`:

```python
from app.languages import (
    DEFAULT_LANGUAGE_CODE,
    SUPPORTED_LANGUAGES,
    is_supported_language_code,
)


def test_supported_languages_include_default_american_english():
    assert DEFAULT_LANGUAGE_CODE == "a"
    assert SUPPORTED_LANGUAGES[0]["code"] == "a"
    assert "American English" in SUPPORTED_LANGUAGES[0]["label"]


def test_language_code_validation_accepts_known_codes():
    assert is_supported_language_code("a") is True
    assert is_supported_language_code("z") is True


def test_language_code_validation_rejects_unknown_codes():
    assert is_supported_language_code("") is False
    assert is_supported_language_code("xx") is False
```

- [ ] **Step 2: Write failing text cleanup test**

Create `tests/test_text.py`:

```python
from app.text import clean_text


def test_clean_text_removes_think_blocks_and_trims_whitespace():
    text = "\n  <think>hidden reasoning</think>\n  Final summary.  \n"

    result = clean_text(text)

    assert result == "Final summary."


def test_clean_text_preserves_text_without_think_blocks():
    assert clean_text("  Keep this text.  ") == "Keep this text."
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_languages.py tests/test_text.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app'`.

- [ ] **Step 4: Create backend package marker**

Create `app/__init__.py`:

```python
"""Backend package for the text-to-speech app."""
```

- [ ] **Step 5: Implement language module**

Create `app/languages.py`:

```python
DEFAULT_LANGUAGE_CODE = "a"

SUPPORTED_LANGUAGES = [
    {"label": "🇺🇸 American English", "code": "a"},
    {"label": "🇬🇧 British English", "code": "b"},
    {"label": "🇪🇸 Spanish", "code": "e"},
    {"label": "🇫🇷 French", "code": "f"},
    {"label": "🇮🇳 Hindi", "code": "h"},
    {"label": "🇮🇹 Italian", "code": "i"},
    {"label": "🇯🇵 Japanese", "code": "j"},
    {"label": "🇧🇷 Brazilian Portuguese", "code": "p"},
    {"label": "🇨🇳 Mandarin Chinese", "code": "z"},
]

SUPPORTED_LANGUAGE_CODES = {language["code"] for language in SUPPORTED_LANGUAGES}


def is_supported_language_code(language_code: str) -> bool:
    return language_code in SUPPORTED_LANGUAGE_CODES
```

- [ ] **Step 6: Implement text module**

Create `app/text.py`:

```python
import re

from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

SUMMARY_TEMPLATE = """
Summarize the following text by highlighting the key points.
Maintain a conversational tone and keep the summary easy to follow for a general audience.
Text: {text}
"""


def clean_text(text: str) -> str:
    cleaned_text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return cleaned_text.strip()


def summarize_text(text: str, model_name: str = "deepseek-r1:8b") -> str:
    prompt = ChatPromptTemplate.from_template(SUMMARY_TEMPLATE)
    chain = prompt | ChatOllama(model=model_name)

    summary = chain.invoke({"text": text})
    return clean_text(summary.content)
```

- [ ] **Step 7: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/test_languages.py tests/test_text.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add app/__init__.py app/languages.py app/text.py tests/test_languages.py tests/test_text.py
git commit -m "feat: add backend domain modules"
```

## Task 3: FastAPI Backend

**Files:**
- Create: `app/models.py`
- Create: `app/audio.py`
- Create: `app/main.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_api.py`:

```python
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint_returns_ok():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_languages_endpoint_returns_supported_languages():
    response = client.get("/api/languages")

    assert response.status_code == 200
    languages = response.json()
    assert languages[0]["code"] == "a"
    assert "American English" in languages[0]["label"]


def test_create_audio_rejects_blank_text():
    response = client.post(
        "/api/audio",
        json={"text": "   ", "language_code": "a", "summarize": False},
    )

    assert response.status_code == 422


def test_create_audio_rejects_unsupported_language_code():
    response = client.post(
        "/api/audio",
        json={"text": "Hello", "language_code": "xx", "summarize": False},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Unsupported language code"


def test_create_audio_returns_audio_url(monkeypatch):
    def fake_generate_audio_file(text: str, language_code: str) -> str:
        assert text == "Hello world"
        assert language_code == "a"
        return "audio.wav"

    monkeypatch.setattr("app.main.generate_audio_file", fake_generate_audio_file)

    response = client.post(
        "/api/audio",
        json={"text": "Hello world", "language_code": "a", "summarize": False},
    )

    assert response.status_code == 200
    assert response.json() == {
        "audio_url": "/audios/audio.wav",
        "summarized_text": None,
    }


def test_create_audio_returns_summary_when_requested(monkeypatch):
    def fake_summarize_text(text: str) -> str:
        assert text == "Long text"
        return "Short summary."

    def fake_generate_audio_file(text: str, language_code: str) -> str:
        assert text == "Short summary."
        assert language_code == "a"
        return "audio.wav"

    monkeypatch.setattr("app.main.summarize_text", fake_summarize_text)
    monkeypatch.setattr("app.main.generate_audio_file", fake_generate_audio_file)

    response = client.post(
        "/api/audio",
        json={"text": "Long text", "language_code": "a", "summarize": True},
    )

    assert response.status_code == 200
    assert response.json() == {
        "audio_url": "/audios/audio.wav",
        "summarized_text": "Short summary.",
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_api.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.main'`.

- [ ] **Step 3: Implement API models**

Create `app/models.py`:

```python
from pydantic import BaseModel, Field, field_validator


class HealthResponse(BaseModel):
    status: str


class LanguageOption(BaseModel):
    label: str
    code: str


class AudioRequest(BaseModel):
    text: str = Field(min_length=1)
    language_code: str = Field(min_length=1)
    summarize: bool = False

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        stripped_value = value.strip()
        if not stripped_value:
            raise ValueError("Text is required")
        return stripped_value


class AudioResponse(BaseModel):
    audio_url: str
    summarized_text: str | None = None
```

- [ ] **Step 4: Implement audio generation boundary**

Create `app/audio.py`:

```python
from pathlib import Path

import numpy as np
import soundfile as sf
from kokoro import KPipeline

AUDIO_DIR = Path(__file__).resolve().parent.parent / "audios"
AUDIO_FILE_NAME = "audio.wav"
AUDIO_SAMPLE_RATE = 24000
VOICE = "af_heart"


def clear_audio_directory(audio_dir: Path = AUDIO_DIR) -> None:
    audio_dir.mkdir(exist_ok=True)

    for file_path in audio_dir.iterdir():
        if file_path.is_file():
            file_path.unlink()


def generate_audio_file(text: str, language_code: str) -> str:
    clear_audio_directory()

    pipeline = KPipeline(lang_code=language_code)
    generator = pipeline(text, voice=VOICE)
    chunks = [audio for _, _, audio in generator]

    if not chunks:
        raise RuntimeError("Kokoro did not generate audio")

    full_audio = np.concatenate(chunks, axis=0)
    sf.write(AUDIO_DIR / AUDIO_FILE_NAME, full_audio, AUDIO_SAMPLE_RATE)

    return AUDIO_FILE_NAME
```

- [ ] **Step 5: Implement FastAPI app**

Create `app/main.py`:

```python
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.audio import AUDIO_DIR, generate_audio_file
from app.languages import SUPPORTED_LANGUAGES, is_supported_language_code
from app.models import AudioRequest, AudioResponse, HealthResponse, LanguageOption
from app.text import summarize_text

app = FastAPI(title="AI Podcaster API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

AUDIO_DIR.mkdir(exist_ok=True)
app.mount("/audios", StaticFiles(directory=AUDIO_DIR), name="audios")


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/api/languages", response_model=list[LanguageOption])
def get_languages() -> list[dict[str, str]]:
    return SUPPORTED_LANGUAGES


@app.post("/api/audio", response_model=AudioResponse)
def create_audio(request: AudioRequest) -> AudioResponse:
    if not is_supported_language_code(request.language_code):
        raise HTTPException(status_code=422, detail="Unsupported language code")

    text_for_audio = request.text
    summarized_text = None

    try:
        if request.summarize:
            summarized_text = summarize_text(request.text)
            text_for_audio = summarized_text

        file_name = generate_audio_file(text_for_audio, request.language_code)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Could not generate audio",
        ) from exc

    return AudioResponse(
        audio_url=f"/audios/{file_name}",
        summarized_text=summarized_text,
    )
```

- [ ] **Step 6: Run API tests to verify they pass**

Run:

```bash
uv run pytest tests/test_api.py -v
```

Expected: PASS.

- [ ] **Step 7: Run all backend tests**

Run:

```bash
uv run pytest -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add app/models.py app/audio.py app/main.py tests/test_api.py
git commit -m "feat: add fastapi backend"
```

## Task 4: Frontend Package And API Client

**Files:**
- Create: `frontend/index.html`
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/types.ts`
- Create: `frontend/src/api.ts`
- Create: `frontend/src/api.test.ts`
- Create: `frontend/src/setupTests.ts`

- [ ] **Step 1: Create frontend package files**

Create `frontend/package.json`:

```json
{
  "name": "text-to-speech-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite --host 127.0.0.1",
    "build": "tsc --noEmit && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.6.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/user-event": "^14.5.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^5.0.0",
    "jsdom": "^26.0.0",
    "typescript": "^5.8.0",
    "vite": "^7.0.0",
    "vitest": "^3.0.0"
  }
}
```

Create `frontend/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>AI Podcaster</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

Create `frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "allowJs": false,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "forceConsistentCasingInFileNames": true,
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx"
  },
  "include": ["src"]
}
```

Create `frontend/tsconfig.node.json`:

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts"]
}
```

Create `frontend/vite.config.ts`:

```ts
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/audios': 'http://127.0.0.1:8000',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/setupTests.ts',
  },
});
```

Create `frontend/src/setupTests.ts`:

```ts
import '@testing-library/jest-dom/vitest';
```

Create `frontend/src/main.tsx` with a temporary render target:

```tsx
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <div>AI Podcaster</div>
  </StrictMode>,
);
```

- [ ] **Step 2: Install frontend dependencies**

Run:

```bash
cd frontend
npm install
```

Expected: `frontend/package-lock.json` is created and dependencies install successfully.

- [ ] **Step 3: Write failing API client tests**

Create `frontend/src/api.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from 'vitest';

import { buildAudioUrl, fetchLanguages, generateAudio } from './api';
import type { AudioRequest } from './types';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('api client', () => {
  it('fetches language options', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [{ label: 'American English', code: 'a' }],
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchLanguages();

    expect(fetchMock).toHaveBeenCalledWith('/api/languages', {
      headers: { Accept: 'application/json' },
    });
    expect(result).toEqual([{ label: 'American English', code: 'a' }]);
  });

  it('posts audio generation requests', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ audio_url: '/audios/audio.wav', summarized_text: null }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const payload: AudioRequest = {
      text: 'Hello',
      language_code: 'a',
      summarize: false,
    };

    const result = await generateAudio(payload);

    expect(fetchMock).toHaveBeenCalledWith('/api/audio', {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });
    expect(result).toEqual({
      audio_url: '/audios/audio.wav',
      summarized_text: null,
    });
  });

  it('turns backend errors into thrown messages', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({ detail: 'Could not generate audio' }),
      }),
    );

    await expect(
      generateAudio({ text: 'Hello', language_code: 'a', summarize: false }),
    ).rejects.toThrow('Could not generate audio');
  });

  it('keeps relative audio URLs relative when no API base URL is configured', () => {
    expect(buildAudioUrl('/audios/audio.wav')).toBe('/audios/audio.wav');
  });
});
```

- [ ] **Step 4: Run API client tests to verify they fail**

Run:

```bash
cd frontend
npm test -- src/api.test.ts
```

Expected: FAIL with an import error for `./api` or `./types`.

- [ ] **Step 5: Implement frontend types**

Create `frontend/src/types.ts`:

```ts
export type LanguageOption = {
  label: string;
  code: string;
};

export type AudioRequest = {
  text: string;
  language_code: string;
  summarize: boolean;
};

export type AudioResponse = {
  audio_url: string;
  summarized_text: string | null;
};
```

- [ ] **Step 6: Implement API client**

Create `frontend/src/api.ts`:

```ts
import type { AudioRequest, AudioResponse, LanguageOption } from './types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

function formatDetail(detail: unknown): string | null {
  if (typeof detail === 'string') {
    return detail;
  }

  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === 'object' && 'msg' in item) {
          return String(item.msg);
        }
        return null;
      })
      .filter(Boolean)
      .join(', ');
  }

  return null;
}

async function request<T>(path: string, init: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;

    try {
      const body = await response.json();
      message = formatDetail(body.detail) ?? message;
    } catch {
      message = `Request failed with status ${response.status}`;
    }

    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

export function fetchLanguages(): Promise<LanguageOption[]> {
  return request<LanguageOption[]>('/api/languages', {
    headers: { Accept: 'application/json' },
  });
}

export function generateAudio(payload: AudioRequest): Promise<AudioResponse> {
  return request<AudioResponse>('/api/audio', {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
}

export function buildAudioUrl(audioUrl: string): string {
  if (/^https?:\/\//.test(audioUrl)) {
    return audioUrl;
  }

  return `${API_BASE_URL}${audioUrl}`;
}
```

- [ ] **Step 7: Run API client tests to verify they pass**

Run:

```bash
cd frontend
npm test -- src/api.test.ts
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/index.html frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/tsconfig.node.json frontend/vite.config.ts frontend/src/main.tsx frontend/src/setupTests.ts frontend/src/types.ts frontend/src/api.ts frontend/src/api.test.ts
git commit -m "feat: add react api client"
```

## Task 5: React App Screen

**Files:**
- Modify: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/App.css`
- Create: `frontend/src/App.test.tsx`

- [ ] **Step 1: Write failing React app tests**

Create `frontend/src/App.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import App from './App';
import { buildAudioUrl, fetchLanguages, generateAudio } from './api';

vi.mock('./api', () => ({
  buildAudioUrl: vi.fn((audioUrl: string) => `http://127.0.0.1:8000${audioUrl}`),
  fetchLanguages: vi.fn(),
  generateAudio: vi.fn(),
}));

const languages = [
  { label: 'American English', code: 'a' },
  { label: 'British English', code: 'b' },
];

beforeEach(() => {
  vi.mocked(buildAudioUrl).mockImplementation(
    (audioUrl: string) => `http://127.0.0.1:8000${audioUrl}`,
  );
  vi.mocked(fetchLanguages).mockResolvedValue(languages);
  vi.mocked(generateAudio).mockResolvedValue({
    audio_url: '/audios/audio.wav',
    summarized_text: null,
  });
});

describe('App', () => {
  it('loads languages and defaults to American English', async () => {
    render(<App />);

    const select = await screen.findByLabelText(/select a language/i);

    expect(select).toHaveValue('a');
    expect(screen.getByRole('option', { name: 'British English' })).toBeInTheDocument();
  });

  it('keeps the generate button disabled for blank text', async () => {
    render(<App />);

    const button = await screen.findByRole('button', { name: /generate audio/i });

    expect(button).toBeDisabled();
  });

  it('submits text and displays the generated audio player', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.type(await screen.findByLabelText(/enter text/i), 'Hello world');
    await user.click(screen.getByRole('button', { name: /generate audio/i }));

    await waitFor(() => {
      expect(generateAudio).toHaveBeenCalledWith({
        text: 'Hello world',
        language_code: 'a',
        summarize: false,
      });
    });

    expect(await screen.findByLabelText(/generated audio/i)).toHaveAttribute(
      'src',
      'http://127.0.0.1:8000/audios/audio.wav',
    );
  });

  it('shows summarized text returned by the backend', async () => {
    const user = userEvent.setup();
    vi.mocked(generateAudio).mockResolvedValue({
      audio_url: '/audios/audio.wav',
      summarized_text: 'Short summary.',
    });

    render(<App />);

    await user.type(await screen.findByLabelText(/enter text/i), 'Long text');
    await user.click(screen.getByLabelText(/summarize text/i));
    await user.click(screen.getByRole('button', { name: /generate audio/i }));

    expect(await screen.findByText('Short summary.')).toBeInTheDocument();
  });

  it('shows API errors', async () => {
    const user = userEvent.setup();
    vi.mocked(generateAudio).mockRejectedValue(new Error('Could not generate audio'));

    render(<App />);

    await user.type(await screen.findByLabelText(/enter text/i), 'Hello');
    await user.click(screen.getByRole('button', { name: /generate audio/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not generate audio');
  });
});
```

- [ ] **Step 2: Run React app tests to verify they fail**

Run:

```bash
cd frontend
npm test -- src/App.test.tsx
```

Expected: FAIL with an import error for `./App`.

- [ ] **Step 3: Implement React app screen**

Create `frontend/src/App.tsx`:

```tsx
import { FormEvent, useEffect, useMemo, useState } from 'react';

import './App.css';
import { buildAudioUrl, fetchLanguages, generateAudio } from './api';
import type { LanguageOption } from './types';

function getInitialLanguage(languages: LanguageOption[]): string {
  return languages.find((language) => language.code === 'a')?.code ?? languages[0]?.code ?? '';
}

export default function App() {
  const [languages, setLanguages] = useState<LanguageOption[]>([]);
  const [languageCode, setLanguageCode] = useState('');
  const [text, setText] = useState('');
  const [summarize, setSummarize] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [summarizedText, setSummarizedText] = useState<string | null>(null);
  const [isLoadingLanguages, setIsLoadingLanguages] = useState(true);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const trimmedText = text.trim();
  const canGenerate = Boolean(trimmedText) && Boolean(languageCode) && !isGenerating;
  const resolvedAudioUrl = useMemo(
    () => (audioUrl ? buildAudioUrl(audioUrl) : null),
    [audioUrl],
  );

  useEffect(() => {
    let isMounted = true;

    async function loadLanguages() {
      try {
        const options = await fetchLanguages();
        if (!isMounted) {
          return;
        }

        setLanguages(options);
        setLanguageCode(getInitialLanguage(options));
      } catch (loadError) {
        if (!isMounted) {
          return;
        }

        setError(
          loadError instanceof Error
            ? loadError.message
            : 'Could not load supported languages',
        );
      } finally {
        if (isMounted) {
          setIsLoadingLanguages(false);
        }
      }
    }

    loadLanguages();

    return () => {
      isMounted = false;
    };
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!canGenerate) {
      return;
    }

    setIsGenerating(true);
    setError(null);
    setAudioUrl(null);
    setSummarizedText(null);

    try {
      const response = await generateAudio({
        text: trimmedText,
        language_code: languageCode,
        summarize,
      });

      setAudioUrl(response.audio_url);
      setSummarizedText(response.summarized_text);
    } catch (generateError) {
      setError(
        generateError instanceof Error
          ? generateError.message
          : 'Could not generate audio',
      );
    } finally {
      setIsGenerating(false);
    }
  }

  return (
    <main className="app-shell">
      <section className="tool-panel" aria-labelledby="app-title">
        <div className="title-block">
          <p className="eyebrow">Text to speech</p>
          <h1 id="app-title">AI Podcaster</h1>
        </div>

        <form className="generator-form" onSubmit={handleSubmit}>
          <label className="field">
            <span>Select a language</span>
            <select
              value={languageCode}
              onChange={(event) => setLanguageCode(event.target.value)}
              disabled={isLoadingLanguages || isGenerating}
            >
              {languages.map((language) => (
                <option key={language.code} value={language.code}>
                  {language.label}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>Enter text</span>
            <textarea
              value={text}
              onChange={(event) => setText(event.target.value)}
              rows={10}
              disabled={isGenerating}
            />
          </label>

          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={summarize}
              onChange={(event) => setSummarize(event.target.checked)}
              disabled={isGenerating}
            />
            <span>Summarize text</span>
          </label>

          <button type="submit" disabled={!canGenerate}>
            {isGenerating ? 'Generating...' : 'Generate Audio'}
          </button>
        </form>

        {error ? (
          <p className="error-message" role="alert">
            {error}
          </p>
        ) : null}

        {resolvedAudioUrl ? (
          <section className="result-panel" aria-label="Generated result">
            <audio aria-label="Generated audio" controls src={resolvedAudioUrl} />

            {summarizedText ? (
              <div className="summary-panel">
                <h2>Generated text</h2>
                <p>{summarizedText}</p>
              </div>
            ) : null}
          </section>
        ) : null}
      </section>
    </main>
  );
}
```

- [ ] **Step 4: Implement app styling**

Create `frontend/src/App.css`:

```css
:root {
  color: #1f2933;
  background: #f4f7f8;
  font-family:
    Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI",
    sans-serif;
  font-synthesis: none;
  text-rendering: optimizeLegibility;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-width: 320px;
  min-height: 100vh;
}

button,
select,
textarea {
  font: inherit;
}

.app-shell {
  min-height: 100vh;
  padding: 32px 20px;
}

.tool-panel {
  width: min(920px, 100%);
  margin: 0 auto;
  padding: 28px;
  border: 1px solid #d6dee2;
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 18px 45px rgb(22 36 45 / 10%);
}

.title-block {
  margin-bottom: 24px;
}

.eyebrow {
  margin: 0 0 6px;
  color: #4f6f52;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}

h1,
h2,
p {
  margin-top: 0;
}

h1 {
  margin-bottom: 0;
  color: #10212b;
  font-size: 2.75rem;
  line-height: 1.05;
  letter-spacing: 0;
}

.generator-form {
  display: grid;
  gap: 18px;
}

.field {
  display: grid;
  gap: 8px;
  font-weight: 650;
}

select,
textarea {
  width: 100%;
  border: 1px solid #c8d3d8;
  border-radius: 6px;
  background: #ffffff;
  color: #1f2933;
}

select {
  min-height: 44px;
  padding: 0 12px;
}

textarea {
  min-height: 220px;
  resize: vertical;
  padding: 12px;
  line-height: 1.5;
}

select:focus,
textarea:focus,
button:focus-visible {
  outline: 3px solid #8bc5b4;
  outline-offset: 2px;
}

.checkbox-row {
  display: flex;
  align-items: center;
  gap: 10px;
  width: fit-content;
  color: #273a43;
  font-weight: 650;
}

.checkbox-row input {
  width: 18px;
  height: 18px;
  accent-color: #2f7d67;
}

button {
  justify-self: start;
  min-height: 44px;
  padding: 0 18px;
  border: 0;
  border-radius: 6px;
  background: #2f7d67;
  color: #ffffff;
  font-weight: 750;
  cursor: pointer;
}

button:hover:not(:disabled) {
  background: #286b58;
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.error-message {
  margin: 20px 0 0;
  padding: 12px 14px;
  border-left: 4px solid #c2410c;
  border-radius: 6px;
  background: #fff3ed;
  color: #8a2f0a;
}

.result-panel {
  display: grid;
  gap: 18px;
  margin-top: 24px;
}

audio {
  width: 100%;
}

.summary-panel {
  padding: 16px;
  border: 1px solid #d6dee2;
  border-radius: 8px;
  background: #f8fbfb;
}

.summary-panel h2 {
  margin-bottom: 8px;
  font-size: 1rem;
  letter-spacing: 0;
}

.summary-panel p {
  margin-bottom: 0;
  line-height: 1.55;
}

@media (max-width: 640px) {
  .app-shell {
    padding: 16px 12px;
  }

  .tool-panel {
    padding: 18px;
  }

  h1 {
    font-size: 2rem;
  }

  button {
    width: 100%;
  }
}
```

- [ ] **Step 5: Wire React entry point to App**

Modify `frontend/src/main.tsx`:

```tsx
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import App from './App';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

- [ ] **Step 6: Run React app tests to verify they pass**

Run:

```bash
cd frontend
npm test -- src/App.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Run all frontend tests**

Run:

```bash
cd frontend
npm test
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/App.tsx frontend/src/App.css frontend/src/App.test.tsx frontend/src/main.tsx
git commit -m "feat: add react text to speech screen"
```

## Task 6: Remove Streamlit Entry Point And Document Development

**Files:**
- Delete: `main.py`
- Modify: `README.md`
- Modify: `.gitignore`
- Modify: `pyrightconfig.json`

- [ ] **Step 1: Verify Streamlit references still exist before cleanup**

Run:

```bash
rg -n "streamlit|st\\." main.py pyproject.toml README.md
```

Expected: at least one match in `main.py`.

- [ ] **Step 2: Delete old Streamlit entry point**

Delete `main.py`.

- [ ] **Step 3: Update README**

Modify `README.md`:

```markdown
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
```

- [ ] **Step 4: Keep Pyright pointed at Python 3.14**

Leave `pyrightconfig.json` as:

```json
{
  "venvPath": ".",
  "venv": ".venv",
  "pythonVersion": "3.14"
}
```

- [ ] **Step 5: Verify Streamlit references are gone from active app code**

Run:

```bash
rg -n "streamlit|st\\." . --glob '!uv.lock' --glob '!docs/superpowers/**'
```

Expected: no matches.

- [ ] **Step 6: Run backend and frontend tests**

Run:

```bash
uv run pytest
cd frontend
npm test
```

Expected: both commands PASS.

- [ ] **Step 7: Commit**

```bash
git add README.md .gitignore pyrightconfig.json
git rm main.py
git commit -m "chore: remove streamlit entry point"
```

## Task 7: Final Verification

**Files:**
- Inspect: all changed files

- [ ] **Step 1: Run backend tests**

Run:

```bash
uv run pytest -v
```

Expected: PASS.

- [ ] **Step 2: Run frontend tests**

Run:

```bash
cd frontend
npm test
```

Expected: PASS.

- [ ] **Step 3: Build the frontend**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS and `frontend/dist/` is generated.

- [ ] **Step 4: Start the backend dev server**

Run:

```bash
uv run uvicorn app.main:app --reload --port 8000
```

Expected: Uvicorn starts and listens on `http://127.0.0.1:8000`.

- [ ] **Step 5: Verify backend health from another terminal**

Run:

```bash
curl -fsS http://127.0.0.1:8000/api/health
```

Expected:

```json
{"status":"ok"}
```

- [ ] **Step 6: Start the frontend dev server**

Run:

```bash
cd frontend
npm run dev
```

Expected: Vite starts and prints a local URL, usually `http://127.0.0.1:5173/`.

- [ ] **Step 7: Verify the frontend can be served**

Run:

```bash
curl -fsS http://127.0.0.1:5173/
```

Expected: HTML containing `AI Podcaster`.

- [ ] **Step 8: Inspect git status**

Run:

```bash
git status --short
```

Expected: no unstaged or untracked source changes except local generated files ignored by git.

- [ ] **Step 9: Leave final verification with a clean worktree**

If final verification required source edits, return to the task that owns those files, update its tests and implementation, rerun Task 7 from Step 1, and commit with that task's commit message. If no source edits were required, create no commit.

## Self-Review

Spec coverage:

- Same current feature set is covered by Tasks 2, 3, 4, and 5.
- FastAPI backend is covered by Tasks 1, 2, and 3.
- Vite React frontend is covered by Tasks 4 and 5.
- Streamlit removal is covered by Task 6.
- README and generated audio ignore rules are covered by Task 6.
- Final backend, frontend, and dev-server verification is covered by Task 7.

Type consistency:

- Backend request shape is `text`, `language_code`, and `summarize` in `app.models.AudioRequest`, `tests/test_api.py`, `frontend/src/types.ts`, `frontend/src/api.ts`, and `frontend/src/App.tsx`.
- Backend response shape is `audio_url` and `summarized_text` in `app.models.AudioResponse`, `tests/test_api.py`, `frontend/src/types.ts`, and React tests.
- Language option shape is `label` and `code` in backend route responses and frontend types.
