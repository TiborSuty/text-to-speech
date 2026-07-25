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
