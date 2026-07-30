import asyncio

from contextlib import asynccontextmanager

import json

from collections.abc import AsyncIterator

from typing import Annotated

from datetime import UTC, datetime, timedelta

from threading import Lock


from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Response

from fastapi.middleware.cors import CORSMiddleware

from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse


from app.audio import (
    AUDIO_DIR,
    AudioGenerationCancelled,
    delete_audio_file,
    delete_expired_audio_files,
    generate_audio_file,
    generate_segmented_audio_file,
)
from app.audio_formats import (
    get_audio_format_from_file_name,
    get_audio_format_spec,
)

from app.config import AppSettings, settings

from app.jobs import (
    TERMINAL_JOB_STATUSES,
    AudioJob,
    complete_audio_job_record,
    create_audio_job_record,
    delete_audio_job_record,
    fail_audio_job_record,
    finalize_audio_job_cancellation,
    get_audio_job_record,
    initialize_audio_job_store,
    list_audio_job_records,
    list_completed_audio_job_records,
    mark_audio_job_output_missing,
    recover_interrupted_audio_jobs,
    remove_expired_audio_job_records,
    request_audio_job_cancellation,
    update_audio_job_progress,
    update_audio_job_status,
)

from app.languages import (
    SUPPORTED_LANGUAGES,
    get_default_voice,
    is_supported_language_code,
    is_supported_voice,
)

from app.models import (
    AUDIO_MAX_TEXT_CHARACTERS,
    AppConfigResponse,
    AudioJobCreateResponse,
    AudioJobStatusResponse,
    AudioRequest,
    AudioResponse,
    HealthResponse,
    LanguageOption,
    PodcastScriptRequest,
    PodcastScriptResponse,
    PodcastWorkflowApprovalRequest,
    PodcastWorkflowResponse,
)

from app.services.audio_generation import AudioGenerationService
from app.services.podcast import build_podcast_audio_request

from app.text import (
    PodcastScriptError,
    SummarizationError,
    create_podcast_script,
    summarize_text,
)

from app.storage import AudioObjectStorage, create_audio_object_storage

from app.worker import AudioJobTask, AudioWorkerPool, get_audio_worker_count

from app.workflow import (
    PodcastWorkflowError,
    PodcastWorkflowNotFoundError,
    approve_podcast_workflow,
    get_podcast_workflow,
    get_podcast_workflow_approval,
    link_podcast_audio_job,
    start_podcast_workflow,
)


audio_storage = create_audio_object_storage()

api_router = APIRouter(prefix="/api")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:

    AUDIO_DIR.mkdir(exist_ok=True)

    initialize_audio_job_store()

    audio_storage.initialize()

    recover_interrupted_audio_jobs()

    reconcile_audio_job_storage()

    cleanup_expired_audio_jobs()

    audio_worker_pool.start()

    try:
        yield

    finally:
        audio_worker_pool.shutdown()


AUDIO_RETENTION_HOURS = settings.audio_retention_hours


def audio_job_to_response(job: AudioJob) -> AudioJobStatusResponse:

    return AudioJobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        queue_position=(
            audio_worker_pool.queue_position(job.job_id)
            if job.status == "queued"
            else None
        ),
        progress=job.progress,
        language_code=job.language_code,
        voice=job.voice,
        summarize=job.summarize,
        audio_format=job.audio_format,
        text_preview=job.text_preview,
        created_at=job.created_at,
        updated_at=job.updated_at,
        audio_url=job.audio_url,
        summarized_text=job.summarized_text,
        error=job.error,
    )


def get_existing_audio_job(job_id: str) -> AudioJob:

    job = get_audio_job_record(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Audio job not found")

    return job


def delete_audio_for_job(job: AudioJob) -> None:

    if job.object_key is None:
        return

    audio_storage.delete(job.object_key)


def store_generated_audio_file(file_name: str) -> str:

    object_key = file_name

    source_path = AUDIO_DIR / file_name

    try:
        audio_storage.put_file(source_path, object_key)

    finally:
        stored_local_path = audio_storage.local_path(object_key)

        if (
            stored_local_path is None
            or stored_local_path.resolve() != source_path.resolve()
        ):
            delete_audio_file(file_name)

    return object_key


def cleanup_expired_audio_jobs() -> None:

    if AUDIO_RETENTION_HOURS <= 0:
        return

    cutoff = datetime.now(UTC) - timedelta(hours=AUDIO_RETENTION_HOURS)

    expired_jobs = remove_expired_audio_job_records(cutoff)

    for job in expired_jobs:
        delete_audio_for_job(job)

    delete_expired_audio_files(cutoff)


def reconcile_audio_job_storage(
    storage: AudioObjectStorage | None = None,
) -> None:

    selected_storage = storage or audio_storage

    for job in list_completed_audio_job_records():
        if job.object_key is None:
            continue

        if selected_storage.exists(job.object_key):
            continue

        mark_audio_job_output_missing(job.job_id)


def resolve_audio_voice(request: AudioRequest) -> str:

    if not is_supported_language_code(request.language_code):
        raise HTTPException(status_code=422, detail="Unsupported language code")

    voice = request.voice or get_default_voice(request.language_code)

    if voice is None or not is_supported_voice(request.language_code, voice):
        raise HTTPException(
            status_code=422,
            detail="Unsupported voice for selected language",
        )

    for segment in request.segments or []:
        if not is_supported_voice(request.language_code, segment.voice):
            raise HTTPException(
                status_code=422,
                detail="Unsupported segment voice for selected language",
            )

    return voice


def get_audio_generation_service() -> AudioGenerationService:
    return AudioGenerationService(
        summarize_text=summarize_text,
        generate_audio_file=generate_audio_file,
        generate_segmented_audio_file=generate_segmented_audio_file,
    )


AudioGenerationServiceDependency = Annotated[
    AudioGenerationService,
    Depends(get_audio_generation_service),
]


def finish_audio_job_cancellation(
    job_id: str,
    file_name: str | None = None,
    object_key: str | None = None,
) -> bool:

    job = get_audio_job_record(job_id)

    if job is None:
        return True

    if job.status not in {"cancel_requested", "cancelled"}:
        return False

    try:
        if object_key is not None:
            audio_storage.delete(object_key)

        elif file_name is not None:
            delete_audio_file(file_name)

    finally:
        finalize_audio_job_cancellation(job_id)

    return True


def run_audio_job(job_id: str, request: AudioRequest, voice: str) -> None:

    service = get_audio_generation_service()

    file_name = None
    object_key = None

    if finish_audio_job_cancellation(job_id):
        return

    try:
        if request.summarize:
            if not update_audio_job_status(job_id, "summarizing"):
                finish_audio_job_cancellation(job_id)
                return

        prepared_audio = service.prepare(request)

        if request.summarize and finish_audio_job_cancellation(job_id):
            return

        if not update_audio_job_status(job_id, "generating"):
            finish_audio_job_cancellation(job_id)
            return

        def report_audio_progress(progress: int) -> bool:

            return update_audio_job_progress(job_id, progress)

        file_name = service.render(
            request,
            voice,
            text=prepared_audio.text,
            output_id=job_id,
            progress_callback=report_audio_progress,
        )

        if finish_audio_job_cancellation(job_id, file_name=file_name):
            return

        object_key = store_generated_audio_file(file_name)

        if finish_audio_job_cancellation(job_id, object_key=object_key):
            return

        if not complete_audio_job_record(
            job_id,
            object_key,
            prepared_audio.summarized_text,
        ):
            finish_audio_job_cancellation(job_id, object_key=object_key)

    except SummarizationError as exc:
        if not finish_audio_job_cancellation(job_id, file_name, object_key):
            fail_audio_job_record(job_id, str(exc))

    except AudioGenerationCancelled:
        finish_audio_job_cancellation(job_id, file_name, object_key)

    except Exception:
        if not finish_audio_job_cancellation(job_id, file_name, object_key):
            fail_audio_job_record(job_id, "Could not generate audio")


def fail_unhandled_audio_job(job_id: str) -> None:

    fail_audio_job_record(job_id, "Could not generate audio")


audio_worker_pool = AudioWorkerPool(
    processor=run_audio_job,
    worker_count=get_audio_worker_count(),
    error_handler=fail_unhandled_audio_job,
)

audio_job_enqueue_lock = Lock()


def format_audio_job_event(job: AudioJob) -> str:

    response = audio_job_to_response(job)

    data = json.dumps(response.model_dump(mode="json"), separators=(",", ":"))

    return f"retry: 1000\ndata: {data}\n\n"


async def stream_audio_job_events(job_id: str) -> AsyncIterator[str]:

    last_event = None

    while True:
        job = get_existing_audio_job(job_id)

        event = format_audio_job_event(job)

        if event != last_event:
            last_event = event

            yield event

        if job.status in TERMINAL_JOB_STATUSES:
            break

        await asyncio.sleep(0.25)


@api_router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:

    return HealthResponse(status="ok")


@api_router.get("/config", response_model=AppConfigResponse)
def get_app_config() -> AppConfigResponse:

    return AppConfigResponse(max_text_characters=AUDIO_MAX_TEXT_CHARACTERS)


@api_router.get("/languages", response_model=list[LanguageOption])
def get_languages() -> list[dict[str, object]]:

    return SUPPORTED_LANGUAGES


@api_router.post("/podcast-scripts", response_model=PodcastScriptResponse)
def generate_podcast_script(
    request: PodcastScriptRequest,
) -> PodcastScriptResponse:

    try:
        return create_podcast_script(request)

    except PodcastScriptError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@api_router.post("/podcast-workflows", response_model=PodcastWorkflowResponse)
def create_podcast_workflow(
    request: PodcastScriptRequest,
) -> PodcastWorkflowResponse:

    try:
        return start_podcast_workflow(request)

    except PodcastWorkflowError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@api_router.get(
    "/podcast-workflows/{workflow_id}",
    response_model=PodcastWorkflowResponse,
)
def read_podcast_workflow(workflow_id: str) -> PodcastWorkflowResponse:

    try:
        return get_podcast_workflow(workflow_id)

    except PodcastWorkflowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    except PodcastWorkflowError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def enqueue_audio_job(
    request: AudioRequest,
    *,
    job_id: str | None = None,
) -> AudioJobCreateResponse:

    with audio_job_enqueue_lock:
        if job_id is not None and get_audio_job_record(job_id) is not None:
            return AudioJobCreateResponse(job_id=job_id)

        voice = resolve_audio_voice(request)

        cleanup_expired_audio_jobs()

        job = create_audio_job_record(
            language_code=request.language_code,
            voice=voice,
            text=request.text,
            summarize=request.summarize,
            audio_format=request.audio_format,
            job_id=job_id,
        )

        audio_worker_pool.submit(
            AudioJobTask(
                job_id=job.job_id,
                request=request,
                voice=voice,
            )
        )

        return AudioJobCreateResponse(job_id=job.job_id)


@api_router.post(
    "/podcast-workflows/{workflow_id}/approve",
    response_model=AudioJobCreateResponse,
    status_code=202,
)
def approve_and_create_podcast_audio(
    workflow_id: str,
    approval: PodcastWorkflowApprovalRequest,
) -> AudioJobCreateResponse:

    preview_request = build_podcast_audio_request(approval)

    resolve_audio_voice(preview_request)

    try:
        approve_podcast_workflow(workflow_id, approval)

        persisted_approval = get_podcast_workflow_approval(workflow_id)

    except PodcastWorkflowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    except PodcastWorkflowError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    audio_request = build_podcast_audio_request(persisted_approval)

    response = enqueue_audio_job(audio_request, job_id=workflow_id)

    try:
        link_podcast_audio_job(workflow_id, response.job_id)

    except PodcastWorkflowError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return response


@api_router.post(
    "/audio-jobs",
    response_model=AudioJobCreateResponse,
    status_code=202,
)
def create_audio_job(
    request: AudioRequest,
) -> AudioJobCreateResponse:

    return enqueue_audio_job(request)


@api_router.get("/audio-jobs", response_model=list[AudioJobStatusResponse])
def get_audio_jobs(
    limit: int = Query(default=20, ge=1, le=100),
) -> list[AudioJobStatusResponse]:

    cleanup_expired_audio_jobs()

    return [audio_job_to_response(job) for job in list_audio_job_records(limit)]


@api_router.get(
    "/audio-jobs/{job_id}",
    response_model=AudioJobStatusResponse,
)
def get_audio_job(job_id: str) -> AudioJobStatusResponse:

    job = get_existing_audio_job(job_id)

    return audio_job_to_response(job)


@api_router.post(
    "/audio-jobs/{job_id}/cancel",
    response_model=AudioJobStatusResponse,
)
def cancel_audio_job(job_id: str) -> AudioJobStatusResponse:

    job = request_audio_job_cancellation(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Audio job not found")

    audio_worker_pool.cancel_pending(job_id)

    return audio_job_to_response(job)


def build_audio_object_response(
    object_key: str,
    download_filename: str | None = None,
) -> Response:

    if not audio_storage.exists(object_key):
        raise HTTPException(status_code=404, detail="Audio file not found")

    presigned_url = audio_storage.presigned_get_url(
        object_key,
        download_filename,
    )

    if presigned_url is not None:
        return RedirectResponse(url=presigned_url, status_code=307)

    file_path = audio_storage.local_path(object_key)

    if file_path is None or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Audio file not found")

    return FileResponse(
        path=file_path,
        media_type=get_audio_format_spec(
            get_audio_format_from_file_name(object_key)
        ).media_type,
        filename=download_filename,
    )


@api_router.get("/audio-files/{object_key}")
def play_audio_file(object_key: str) -> Response:

    return build_audio_object_response(object_key)


@api_router.get("/audio-jobs/{job_id}/download")
def download_audio_job(job_id: str) -> Response:

    job = get_existing_audio_job(job_id)

    if job.status != "done" or job.object_key is None:
        raise HTTPException(status_code=404, detail="Audio file not found")

    return build_audio_object_response(
        job.object_key,
        download_filename=job.object_key,
    )


@api_router.get("/audio-jobs/{job_id}/events")
def get_audio_job_events(job_id: str) -> StreamingResponse:

    get_existing_audio_job(job_id)

    return StreamingResponse(
        stream_audio_job_events(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@api_router.delete("/audio-jobs/{job_id}", status_code=204)
def delete_audio_job(job_id: str) -> Response:

    job = get_existing_audio_job(job_id)

    if job.status not in TERMINAL_JOB_STATUSES:
        raise HTTPException(
            status_code=409, detail="Active audio jobs cannot be deleted"
        )

    delete_audio_for_job(job)

    deleted_job = delete_audio_job_record(job_id)

    if deleted_job is None:
        raise HTTPException(status_code=404, detail="Audio job not found")

    return Response(status_code=204)


@api_router.post("/audio", response_model=AudioResponse)
def create_audio(
    request: AudioRequest,
    service: AudioGenerationServiceDependency,
) -> AudioResponse:

    voice = resolve_audio_voice(request)

    try:
        prepared_audio = service.prepare(request)
        file_name = service.render(
            request,
            voice,
            text=prepared_audio.text,
        )

        object_key = store_generated_audio_file(file_name)

    except SummarizationError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Could not generate audio",
        ) from exc

    return AudioResponse(
        audio_url=f"/api/audio-files/{object_key}",
        summarized_text=prepared_audio.summarized_text,
    )


def create_app(app_settings: AppSettings = settings) -> FastAPI:
    application = FastAPI(
        title=app_settings.name,
        version=app_settings.version,
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(app_settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(api_router)
    return application


app = create_app()
