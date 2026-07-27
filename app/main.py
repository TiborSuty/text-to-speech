# Imports asyncio so the SSE stream can wait between status checks.
import asyncio
# Imports json so job status payloads can be serialized into SSE messages.
import json
# Imports AsyncIterator for the SSE generator return type.
from collections.abc import AsyncIterator
# Imports Lock so only one audio file generation runs at a time.
from threading import Lock

# Imports FastAPI's background task helper, application class, and HTTP exception helper.
from fastapi import BackgroundTasks, FastAPI, HTTPException
# Imports the middleware used to let the Vite frontend call this API in dev.
from fastapi.middleware.cors import CORSMiddleware
# Imports StreamingResponse so the API can return Server-Sent Events.
from fastapi.responses import StreamingResponse
# Imports FastAPI's static-file server for exposing generated audio files.
from fastapi.staticfiles import StaticFiles

# Imports the audio output directory and the function that writes audio files.
from app.audio import AUDIO_DIR, generate_audio_file
# Imports helpers that store and update asynchronous audio job state.
from app.jobs import (
    TERMINAL_JOB_STATUSES,
    AudioJob,
    complete_audio_job_record,
    create_audio_job_record,
    fail_audio_job_record,
    get_audio_job_record,
    update_audio_job_status,
)
# Imports supported language data and the language-code validation helper.
from app.languages import SUPPORTED_LANGUAGES, is_supported_language_code
# Imports Pydantic models used as request and response schemas.
from app.models import (
    AudioJobCreateResponse,
    AudioJobStatusResponse,
    AudioRequest,
    AudioResponse,
    HealthResponse,
    LanguageOption,
)
# Imports the optional summarization error and function used before audio generation.
from app.text import SummarizationError, summarize_text

# Creates the FastAPI application and gives it a title for API docs.
app = FastAPI(title="AI Podcaster API")

# Registers CORS middleware so browser-based frontend requests are accepted.
app.add_middleware(
    # Tells FastAPI which middleware class to install.
    CORSMiddleware,
    # Lists the local development frontend origins allowed to call the API.
    allow_origins=[
        # Allows Vite when opened through localhost on the default port.
        "http://localhost:5173",
        # Allows Vite when opened through 127.0.0.1 on the default port.
        "http://127.0.0.1:5173",
        # Allows Vite when it falls back to the next development port.
        "http://localhost:5174",
        # Allows the fallback Vite port through the numeric loopback address.
        "http://127.0.0.1:5174",
    ],
    # Allows credentialed requests if the frontend later adds cookies or auth.
    allow_credentials=True,
    # Allows every HTTP method so the POST audio endpoint works from the UI.
    allow_methods=["*"],
    # Allows every request header, including JSON content-type headers.
    allow_headers=["*"],
)

# Ensures the audio output folder exists before it is mounted or written to.
AUDIO_DIR.mkdir(exist_ok=True)
# Serves files in the audio directory under the /audios URL path.
app.mount("/audios", StaticFiles(directory=AUDIO_DIR), name="audios")

# Serializes background audio jobs because the current audio module writes one shared file.
audio_generation_lock = Lock()


# Converts an internal job snapshot into the public API response model.
def audio_job_to_response(job: AudioJob) -> AudioJobStatusResponse:
    # Builds the response payload from the job's current snapshot.
    return AudioJobStatusResponse(
        # Copies the job identifier into the response.
        job_id=job.job_id,
        # Copies the current status into the response.
        status=job.status,
        # Copies the completed audio URL when one exists.
        audio_url=job.audio_url,
        # Copies the completed summary text when one exists.
        summarized_text=job.summarized_text,
        # Copies the failure message when one exists.
        error=job.error,
    )


# Loads one job or raises a 404 response when the ID is unknown.
def get_existing_audio_job(job_id: str) -> AudioJob:
    # Reads the job snapshot from the in-memory store.
    job = get_audio_job_record(job_id)
    # Checks whether the job exists.
    if job is None:
        # Reports unknown job IDs as normal API not-found errors.
        raise HTTPException(status_code=404, detail="Audio job not found")
    # Returns the found job snapshot.
    return job


# Runs the blocking summarization and audio generation work for one job.
def run_audio_job(job_id: str, request: AudioRequest) -> None:
    # Ensures only one job writes to the shared audio output file at a time.
    with audio_generation_lock:
        # Starts with the request text as the content that should become audio.
        text_for_audio = request.text
        # Tracks optional summary text generated before audio.
        summarized_text = None

        # Converts internal failures into job status updates instead of HTTP responses.
        try:
            # Checks whether this job should summarize the text before speech.
            if request.summarize:
                # Marks the job as currently using the local summarizer.
                update_audio_job_status(job_id, "summarizing")
                # Generates the text summary.
                summarized_text = summarize_text(request.text)
                # Uses the summary as the text for speech generation.
                text_for_audio = summarized_text

            # Marks the job as currently generating the audio file.
            update_audio_job_status(job_id, "generating")
            # Generates the audio file and receives its file name.
            file_name = generate_audio_file(text_for_audio, request.language_code)
        # Handles failures from the local Ollama summarization step.
        except SummarizationError as exc:
            # Stores a clear, user-facing summarization failure on the job.
            fail_audio_job_record(job_id, str(exc))
        # Handles any remaining text-to-speech or filesystem failure.
        except Exception:
            # Stores the same stable audio-generation failure message used by the sync endpoint.
            fail_audio_job_record(job_id, "Could not generate audio")
        # Runs only after successful generation.
        else:
            # Stores the final audio URL and optional summary on the job.
            complete_audio_job_record(
                # Identifies which job should be completed.
                job_id,
                # Builds the URL that the frontend can pass to the audio element.
                f"/audios/{file_name}",
                # Preserves the optional summary in the completion event.
                summarized_text,
            )


# Formats one job snapshot as a Server-Sent Event message.
def format_audio_job_event(job: AudioJob) -> str:
    # Converts the job snapshot into the public response model.
    response = audio_job_to_response(job)
    # Serializes the response model to compact JSON.
    data = json.dumps(response.model_dump(), separators=(",", ":"))
    # Wraps the JSON payload in SSE's data-message format.
    return f"data: {data}\n\n"


# Streams job status changes until the job reaches a terminal state.
async def stream_audio_job_events(job_id: str) -> AsyncIterator[str]:
    # Tracks the last payload so duplicate polling results are not resent.
    last_event = None

    # Keeps the stream open until done or failed.
    while True:
        # Reads the latest job snapshot.
        job = get_existing_audio_job(job_id)
        # Formats the latest snapshot as an SSE message.
        event = format_audio_job_event(job)
        # Emits only changed snapshots to reduce unnecessary frontend updates.
        if event != last_event:
            # Stores the event so the next loop can detect duplicates.
            last_event = event
            # Sends the event to the connected browser.
            yield event

        # Stops streaming after the job is done or failed.
        if job.status in TERMINAL_JOB_STATUSES:
            # Leaves the generator after sending the terminal event.
            break

        # Waits briefly before checking job state again.
        await asyncio.sleep(0.25)


# Registers the health-check endpoint and documents its response schema.
@app.get("/api/health", response_model=HealthResponse)
# Handles GET /api/health requests.
def health() -> HealthResponse:
    # Returns a simple status payload so callers know the API is running.
    return HealthResponse(status="ok")


# Registers the language-list endpoint and documents each returned item.
@app.get("/api/languages", response_model=list[LanguageOption])
# Handles GET /api/languages requests.
def get_languages() -> list[dict[str, str]]:
    # Returns the complete list of language labels and Kokoro language codes.
    return SUPPORTED_LANGUAGES


# Registers the async audio-job creation endpoint.
@app.post("/api/audio-jobs", response_model=AudioJobCreateResponse, status_code=202)
# Handles POST /api/audio-jobs requests with a validated JSON request body.
def create_audio_job(
    # Receives the validated audio-generation request.
    request: AudioRequest,
    # Receives FastAPI's background task collector for work after the response.
    background_tasks: BackgroundTasks,
) -> AudioJobCreateResponse:
    # Rejects language codes that are not in the supported language list.
    if not is_supported_language_code(request.language_code):
        # Raises a 422 response so the frontend sees a validation-style error.
        raise HTTPException(status_code=422, detail="Unsupported language code")

    # Creates a queued job record before the background work starts.
    job = create_audio_job_record()
    # Schedules the blocking generation work to run after this response is sent.
    background_tasks.add_task(run_audio_job, job.job_id, request)
    # Returns the job ID immediately so the frontend can open an SSE connection.
    return AudioJobCreateResponse(job_id=job.job_id)


# Registers a polling-friendly status endpoint for async audio jobs.
@app.get("/api/audio-jobs/{job_id}", response_model=AudioJobStatusResponse)
# Handles GET /api/audio-jobs/{job_id} requests.
def get_audio_job(job_id: str) -> AudioJobStatusResponse:
    # Loads the job or raises 404 when it does not exist.
    job = get_existing_audio_job(job_id)
    # Returns the current job status payload.
    return audio_job_to_response(job)


# Registers the Server-Sent Events endpoint for async audio job updates.
@app.get("/api/audio-jobs/{job_id}/events")
# Handles GET /api/audio-jobs/{job_id}/events requests.
def get_audio_job_events(job_id: str) -> StreamingResponse:
    # Validates the job ID before opening a streaming response.
    get_existing_audio_job(job_id)
    # Returns a streaming response that EventSource can consume.
    return StreamingResponse(
        # Streams status payloads until the job reaches done or failed.
        stream_audio_job_events(job_id),
        # Uses the SSE content type expected by browsers.
        media_type="text/event-stream",
        # Sends headers that discourage buffering of live events.
        headers={
            # Prevents browsers and proxies from caching live job events.
            "Cache-Control": "no-cache",
            # Hints to reverse proxies that this response should not be buffered.
            "X-Accel-Buffering": "no",
        },
    )


# Registers the audio-generation endpoint and documents its response schema.
@app.post("/api/audio", response_model=AudioResponse)
# Handles POST /api/audio requests with a validated JSON request body.
def create_audio(request: AudioRequest) -> AudioResponse:
    # Rejects language codes that are not in the supported language list.
    if not is_supported_language_code(request.language_code):
        # Raises a 422 response so the frontend sees a validation-style error.
        raise HTTPException(status_code=422, detail="Unsupported language code")

    # Starts with the user-provided text as the text that will become audio.
    text_for_audio = request.text
    # Tracks the generated summary, or stays None when summarization is off.
    summarized_text = None

    # Wraps summarization and audio generation so internal failures become HTTP errors.
    try:
        # Checks whether the caller requested text summarization before speech.
        if request.summarize:
            # Produces a shorter version of the submitted text.
            summarized_text = summarize_text(request.text)
            # Uses the summary, rather than the original text, for audio generation.
            text_for_audio = summarized_text

        # Generates the audio file and receives the file name to expose in the response.
        file_name = generate_audio_file(text_for_audio, request.language_code)
    # Handles failures from the local Ollama summarization step.
    except SummarizationError as exc:
        # Raises a 503 response because the local summarizer dependency is unavailable.
        raise HTTPException(
            # Marks the failure as an unavailable local dependency.
            status_code=503,
            # Sends the actionable summarization setup message to the frontend.
            detail=str(exc),
        # Chains the summarization exception for server-side debugging.
        ) from exc
    # Converts any summarizer or TTS exception into an API response.
    except Exception as exc:
        # Raises a 500 response while preserving the original exception as the cause.
        raise HTTPException(
            # Marks the failure as an internal server error.
            status_code=500,
            # Sends a stable user-facing error message.
            detail="Could not generate audio",
        # Chains the original exception for server-side debugging.
        ) from exc

    # Builds the successful response payload for the frontend.
    return AudioResponse(
        # Provides the browser-accessible URL for the generated audio file.
        audio_url=f"/audios/{file_name}",
        # Includes the summary only when summarization was requested.
        summarized_text=summarized_text,
    )
