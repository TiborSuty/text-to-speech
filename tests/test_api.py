import time
from threading import Event

from fastapi.testclient import TestClient

from app.audio import AUDIO_DIR
from app.main import app
from app.models import (
    AUDIO_MAX_TEXT_CHARACTERS,
    AudioJobCreateResponse,
    PodcastScriptResponse,
    PodcastWorkflowApprovalRequest,
    PodcastWorkflowResponse,
)
from app.text import PodcastScriptError, SummarizationError

client = TestClient(app)


def wait_for_job_status(
    job_id: str,
    expected_statuses: set[str] | None = None,
    timeout: float = 3,
) -> dict[str, object]:

    statuses = expected_statuses or {"cancelled", "done", "failed"}

    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        response = client.get(f"/api/audio-jobs/{job_id}")

        job = response.json()

        if job["status"] in statuses:
            return job

        time.sleep(0.01)

    raise AssertionError(
        f"Job {job_id} did not reach {sorted(statuses)} before timeout"
    )


def test_health_endpoint_returns_ok():

    response = client.get("/api/health")

    assert response.status_code == 200

    assert response.json() == {"status": "ok"}


def test_config_endpoint_returns_text_limit():

    response = client.get("/api/config")

    assert response.status_code == 200
    assert response.json() == {"max_text_characters": AUDIO_MAX_TEXT_CHARACTERS}


def test_audio_job_rejects_text_over_configured_limit():

    response = client.post(
        "/api/audio-jobs",
        json={
            "text": "x" * (AUDIO_MAX_TEXT_CHARACTERS + 1),
            "language_code": "a",
            "summarize": False,
        },
    )

    assert response.status_code == 422
    assert "at most" in response.json()["detail"][0]["msg"]


def test_languages_endpoint_returns_supported_languages():

    response = client.get("/api/languages")

    assert response.status_code == 200

    languages = response.json()

    assert languages[0]["code"] == "a"

    assert "American English" in languages[0]["label"]

    assert languages[0]["default_voice"] == "af_heart"

    assert {"id": "af_heart", "label": "Heart (Female)"} in languages[0]["voices"]


def test_generate_podcast_script_endpoint(monkeypatch):

    def fake_create_podcast_script(request):

        assert request.text == "SQLite runs inside your application."
        assert request.format == "interview"
        assert request.duration == "short"

        return PodcastScriptResponse(
            title="Inside SQLite",
            segments=[
                {"speaker": "host", "text": "Where does SQLite run?"},
                {
                    "speaker": "guest",
                    "text": "It runs inside the application process.",
                },
            ],
        )

    monkeypatch.setattr(
        "app.main.create_podcast_script",
        fake_create_podcast_script,
    )

    response = client.post(
        "/api/podcast-scripts",
        json={
            "text": "SQLite runs inside your application.",
            "format": "interview",
            "duration": "short",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "title": "Inside SQLite",
        "segments": [
            {"speaker": "host", "text": "Where does SQLite run?"},
            {
                "speaker": "guest",
                "text": "It runs inside the application process.",
            },
        ],
    }


def test_generate_podcast_script_reports_ollama_unavailable(monkeypatch):

    def fake_create_podcast_script(_request):
        raise PodcastScriptError("Podcast Director is unavailable")

    monkeypatch.setattr(
        "app.main.create_podcast_script",
        fake_create_podcast_script,
    )

    response = client.post(
        "/api/podcast-scripts",
        json={
            "text": "Source material",
            "format": "explainer",
            "duration": "medium",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Podcast Director is unavailable"


def test_create_podcast_workflow_endpoint(monkeypatch):

    def fake_start_podcast_workflow(request):

        assert request.text == "SQLite is embedded."
        assert request.format == "narration"
        assert request.duration == "short"

        return PodcastWorkflowResponse(
            workflow_id="workflow123",
            status="awaiting_review",
            script={
                "title": "Embedded SQLite",
                "segments": [{"speaker": "host", "text": "SQLite is embedded."}],
            },
            facts=["SQLite is embedded."],
            issues=[],
            revision_count=0,
        )

    monkeypatch.setattr(
        "app.main.start_podcast_workflow",
        fake_start_podcast_workflow,
    )

    response = client.post(
        "/api/podcast-workflows",
        json={
            "text": "SQLite is embedded.",
            "format": "narration",
            "duration": "short",
        },
    )

    assert response.status_code == 200
    assert response.json()["workflow_id"] == "workflow123"
    assert response.json()["status"] == "awaiting_review"
    assert response.json()["facts"] == ["SQLite is embedded."]
    assert response.json()["audio_job_id"] is None


def test_approve_podcast_workflow_queues_idempotent_audio(monkeypatch):

    persisted_approval = PodcastWorkflowApprovalRequest(
        script={
            "title": "Inside SQLite",
            "segments": [
                {"speaker": "host", "text": "Where does SQLite run?"},
                {"speaker": "guest", "text": "Inside the application."},
            ],
        },
        language_code="a",
        host_voice="af_heart",
        guest_voice="af_bella",
        audio_format="mp3",
    )

    captured = {}

    def fake_approve(workflow_id, approval):
        assert workflow_id == "workflow123"
        assert approval == persisted_approval

    def fake_get_approval(workflow_id):
        assert workflow_id == "workflow123"
        return persisted_approval

    def fake_enqueue(request, *, job_id=None):
        captured["request"] = request
        captured["job_id"] = job_id
        return AudioJobCreateResponse(job_id=job_id)

    def fake_link(workflow_id, audio_job_id):
        captured["link"] = (workflow_id, audio_job_id)

    monkeypatch.setattr("app.main.approve_podcast_workflow", fake_approve)
    monkeypatch.setattr("app.main.get_podcast_workflow_approval", fake_get_approval)
    monkeypatch.setattr("app.main.enqueue_audio_job", fake_enqueue)
    monkeypatch.setattr("app.main.link_podcast_audio_job", fake_link)

    response = client.post(
        "/api/podcast-workflows/workflow123/approve",
        json=persisted_approval.model_dump(mode="json"),
    )

    assert response.status_code == 202
    assert response.json() == {"job_id": "workflow123"}
    assert captured["job_id"] == "workflow123"
    assert captured["link"] == ("workflow123", "workflow123")

    request = captured["request"]
    assert [segment.voice for segment in request.segments] == [
        "af_heart",
        "af_bella",
    ]
    assert request.summarize is False
    assert request.audio_format == "mp3"


def test_audio_job_generates_multi_speaker_script(monkeypatch):

    captured_segments: list[tuple[str, str]] = []

    def fake_generate_segmented_audio_file(
        segments,
        language_code,
        config,
    ):

        captured_segments.extend(segments)
        assert language_code == "a"

        if config.progress_callback is not None:
            assert config.progress_callback(50) is True

        (AUDIO_DIR / f"{config.output_id}.wav").write_bytes(b"podcast-wave-data")
        return f"{config.output_id}.wav"

    monkeypatch.setattr(
        "app.main.generate_segmented_audio_file",
        fake_generate_segmented_audio_file,
    )

    create_response = client.post(
        "/api/audio-jobs",
        json={
            "text": "Welcome\nThank you",
            "language_code": "a",
            "voice": "af_heart",
            "summarize": False,
            "segments": [
                {
                    "speaker": "host",
                    "text": "Welcome",
                    "voice": "af_heart",
                },
                {
                    "speaker": "guest",
                    "text": "Thank you",
                    "voice": "am_adam",
                },
            ],
        },
    )

    job = wait_for_job_status(create_response.json()["job_id"])

    assert job["status"] == "done"
    assert captured_segments == [
        ("Welcome", "af_heart"),
        ("Thank you", "am_adam"),
    ]


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


def test_create_audio_rejects_voice_language_mismatch():

    response = client.post(
        "/api/audio",
        json={
            "text": "Hello",
            "language_code": "a",
            "voice": "bf_emma",
            "summarize": False,
        },
    )

    assert response.status_code == 422

    assert response.json()["detail"] == "Unsupported voice for selected language"


def test_create_audio_rejects_unsupported_audio_format():

    response = client.post(
        "/api/audio",
        json={
            "text": "Hello",
            "language_code": "a",
            "summarize": False,
            "audio_format": "aac",
        },
    )

    assert response.status_code == 422


def test_create_audio_returns_audio_url(monkeypatch):

    def fake_generate_audio_file(text: str, language_code: str, voice: str) -> str:

        assert text == "Hello world"

        assert language_code == "a"

        assert voice == "af_heart"

        (AUDIO_DIR / "audio.wav").write_bytes(b"test-wave-data")

        return "audio.wav"

    monkeypatch.setattr("app.main.generate_audio_file", fake_generate_audio_file)

    response = client.post(
        "/api/audio",
        json={"text": "Hello world", "language_code": "a", "summarize": False},
    )

    assert response.status_code == 200

    assert response.json() == {
        "audio_url": "/api/audio-files/audio.wav",
        "summarized_text": None,
    }


def test_create_audio_returns_summary_when_requested(monkeypatch):

    def fake_summarize_text(text: str) -> str:

        assert text == "Long text"

        return "Short summary."

    def fake_generate_audio_file(text: str, language_code: str, voice: str) -> str:

        assert text == "Short summary."

        assert language_code == "a"

        assert voice == "af_heart"

        (AUDIO_DIR / "audio.wav").write_bytes(b"test-wave-data")

        return "audio.wav"

    monkeypatch.setattr("app.main.summarize_text", fake_summarize_text)

    monkeypatch.setattr("app.main.generate_audio_file", fake_generate_audio_file)

    response = client.post(
        "/api/audio",
        json={"text": "Long text", "language_code": "a", "summarize": True},
    )

    assert response.status_code == 200

    assert response.json() == {
        "audio_url": "/api/audio-files/audio.wav",
        "summarized_text": "Short summary.",
    }


def test_create_audio_reports_summarizer_unavailable(monkeypatch):

    error_message = "Could not summarize text. Make sure Ollama is running and deepseek-r1:8b is installed."

    def fake_summarize_text(text: str) -> str:

        assert text == "Long text"

        raise SummarizationError(error_message)

    monkeypatch.setattr("app.main.summarize_text", fake_summarize_text)

    response = client.post(
        "/api/audio",
        json={"text": "Long text", "language_code": "a", "summarize": True},
    )

    assert response.status_code == 503

    assert response.json()["detail"] == error_message


def test_create_audio_job_returns_job_id(monkeypatch):

    def fake_generate_audio_file(
        text: str,
        language_code: str,
        voice: str,
        output_id: str,
        progress_callback=None,
    ) -> str:

        assert text == "Hello world"

        assert language_code == "a"

        assert voice == "af_bella"

        (AUDIO_DIR / f"{output_id}.wav").write_bytes(b"test-wave-data")

        return f"{output_id}.wav"

    monkeypatch.setattr("app.main.generate_audio_file", fake_generate_audio_file)

    response = client.post(
        "/api/audio-jobs",
        json={
            "text": "Hello world",
            "language_code": "a",
            "voice": "af_bella",
            "summarize": False,
        },
    )

    assert response.status_code == 202

    job_id = response.json()["job_id"]

    assert isinstance(job_id, str)

    assert job_id

    assert wait_for_job_status(job_id)["status"] == "done"


def test_audio_job_status_returns_completed_job(monkeypatch):

    def fake_generate_audio_file(
        text: str,
        language_code: str,
        voice: str,
        output_id: str,
        progress_callback=None,
    ) -> str:

        assert text == "Hello world"

        assert language_code == "a"

        assert voice == "af_heart"

        (AUDIO_DIR / f"{output_id}.wav").write_bytes(b"test-wave-data")

        return f"{output_id}.wav"

    monkeypatch.setattr("app.main.generate_audio_file", fake_generate_audio_file)

    create_response = client.post(
        "/api/audio-jobs",
        json={"text": "Hello world", "language_code": "a", "summarize": False},
    )

    job_id = create_response.json()["job_id"]

    job = wait_for_job_status(job_id, {"done"})

    assert job["job_id"] == job_id

    assert job["status"] == "done"
    assert job["progress"] == 100

    assert job["audio_url"] == f"/api/audio-files/{job_id}.wav"

    assert job["language_code"] == "a"
    assert job["voice"] == "af_heart"
    assert job["summarize"] is False
    assert job["audio_format"] == "wav"
    assert job["text_preview"] == "Hello world"

    assert job["created_at"]
    assert job["updated_at"]

    assert job["summarized_text"] is None
    assert job["error"] is None


def test_audio_job_reports_incremental_generation_progress(monkeypatch):

    progress_reported = Event()
    release_generation = Event()

    def fake_generate_audio_file(
        text: str,
        language_code: str,
        voice: str,
        output_id: str,
        progress_callback=None,
    ) -> str:
        assert progress_callback is not None
        assert progress_callback(42) is True
        progress_reported.set()
        assert release_generation.wait(timeout=3)
        file_name = f"{output_id}.wav"
        (AUDIO_DIR / file_name).write_bytes(b"test-wave-data")
        return file_name

    monkeypatch.setattr("app.main.generate_audio_file", fake_generate_audio_file)
    create_response = client.post(
        "/api/audio-jobs",
        json={"text": "Track this", "language_code": "a", "summarize": False},
    )
    job_id = create_response.json()["job_id"]

    assert progress_reported.wait(timeout=3)
    active_job = client.get(f"/api/audio-jobs/{job_id}").json()
    assert active_job["status"] == "generating"
    assert active_job["progress"] == 42

    release_generation.set()
    completed_job = wait_for_job_status(job_id, {"done"})
    assert completed_job["progress"] == 100


def test_audio_job_events_stream_done_event(monkeypatch):

    def fake_generate_audio_file(
        text: str,
        language_code: str,
        voice: str,
        output_id: str,
        progress_callback=None,
    ) -> str:

        assert text == "Hello world"

        assert language_code == "a"

        assert voice == "af_heart"

        (AUDIO_DIR / f"{output_id}.wav").write_bytes(b"test-wave-data")

        return f"{output_id}.wav"

    monkeypatch.setattr("app.main.generate_audio_file", fake_generate_audio_file)

    create_response = client.post(
        "/api/audio-jobs",
        json={"text": "Hello world", "language_code": "a", "summarize": False},
    )

    job_id = create_response.json()["job_id"]

    with client.stream("GET", f"/api/audio-jobs/{job_id}/events") as stream_response:
        assert stream_response.status_code == 200

        stream_text = "".join(stream_response.iter_text())

    assert "data: " in stream_text

    assert "retry: 1000" in stream_text

    assert '"status":"done"' in stream_text

    assert f'"audio_url":"/api/audio-files/{job_id}.wav"' in stream_text

    assert '"text_preview":"Hello world"' in stream_text


def test_audio_job_events_stream_failed_summary_event(monkeypatch):

    error_message = "Could not summarize text. Make sure Ollama is running and deepseek-r1:8b is installed."

    def fake_summarize_text(text: str) -> str:

        assert text == "Long text"

        raise SummarizationError(error_message)

    monkeypatch.setattr("app.main.summarize_text", fake_summarize_text)

    create_response = client.post(
        "/api/audio-jobs",
        json={"text": "Long text", "language_code": "a", "summarize": True},
    )

    job_id = create_response.json()["job_id"]

    with client.stream("GET", f"/api/audio-jobs/{job_id}/events") as stream_response:
        assert stream_response.status_code == 200

        stream_text = "".join(stream_response.iter_text())

    assert '"status":"failed"' in stream_text

    assert error_message in stream_text


def test_audio_job_history_download_and_delete_unique_file(monkeypatch):

    def fake_generate_audio_file(
        text: str,
        language_code: str,
        voice: str,
        output_id: str,
        progress_callback=None,
        audio_format="wav",
    ) -> str:

        assert text == "Keep this episode"
        assert language_code == "b"
        assert voice == "bf_emma"
        assert audio_format == "mp3"

        file_name = f"{output_id}.mp3"

        (AUDIO_DIR / file_name).write_bytes(b"test-wave-data")

        return file_name

    monkeypatch.setattr("app.main.generate_audio_file", fake_generate_audio_file)

    create_response = client.post(
        "/api/audio-jobs",
        json={
            "text": "Keep this episode",
            "language_code": "b",
            "voice": "bf_emma",
            "summarize": False,
            "audio_format": "mp3",
        },
    )

    job_id = create_response.json()["job_id"]
    object_key = f"{job_id}.mp3"

    wait_for_job_status(job_id, {"done"})

    from app import main

    assert main.audio_storage.exists(object_key)

    history_response = client.get("/api/audio-jobs?limit=100")
    history_job = next(
        job for job in history_response.json() if job["job_id"] == job_id
    )

    assert history_job["status"] == "done"
    assert history_job["audio_url"] == f"/api/audio-files/{job_id}.mp3"
    assert history_job["language_code"] == "b"
    assert history_job["voice"] == "bf_emma"
    assert history_job["audio_format"] == "mp3"
    assert history_job["text_preview"] == "Keep this episode"

    playback_response = client.get(history_job["audio_url"])

    assert playback_response.status_code == 200
    assert playback_response.headers["content-type"] == "audio/mpeg"
    assert playback_response.content == b"test-wave-data"

    download_response = client.get(f"/api/audio-jobs/{job_id}/download")

    assert download_response.status_code == 200
    assert download_response.headers["content-type"] == "audio/mpeg"
    assert (
        f'filename="{job_id}.mp3"' in download_response.headers["content-disposition"]
    )
    assert download_response.content == b"test-wave-data"

    delete_response = client.delete(f"/api/audio-jobs/{job_id}")

    assert delete_response.status_code == 204

    assert main.audio_storage.exists(object_key) is False

    assert client.get(f"/api/audio-jobs/{job_id}").status_code == 404


def test_queued_audio_job_reports_position_and_cancels(monkeypatch):

    first_job_started = Event()
    release_first_job = Event()
    generated_texts: list[str] = []

    def fake_generate_audio_file(
        text: str,
        language_code: str,
        voice: str,
        output_id: str,
        progress_callback=None,
    ) -> str:

        generated_texts.append(text)

        if text == "First job":
            first_job_started.set()

            assert release_first_job.wait(timeout=3)

        file_name = f"{output_id}.wav"
        (AUDIO_DIR / file_name).write_bytes(b"test-wave-data")
        return file_name

    monkeypatch.setattr("app.main.generate_audio_file", fake_generate_audio_file)

    first_response = client.post(
        "/api/audio-jobs",
        json={"text": "First job", "language_code": "a", "summarize": False},
    )
    first_job_id = first_response.json()["job_id"]
    assert first_job_started.wait(timeout=3)

    second_response = client.post(
        "/api/audio-jobs",
        json={"text": "Second job", "language_code": "a", "summarize": False},
    )
    second_job_id = second_response.json()["job_id"]

    third_response = client.post(
        "/api/audio-jobs",
        json={"text": "Third job", "language_code": "a", "summarize": False},
    )
    third_job_id = third_response.json()["job_id"]

    queued_job = client.get(f"/api/audio-jobs/{second_job_id}").json()
    assert queued_job["status"] == "queued"
    assert queued_job["queue_position"] == 1
    assert client.get(f"/api/audio-jobs/{third_job_id}").json()["queue_position"] == 2

    cancel_response = client.post(f"/api/audio-jobs/{second_job_id}/cancel")
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"
    assert cancel_response.json()["queue_position"] is None

    assert client.get(f"/api/audio-jobs/{third_job_id}").json()["queue_position"] == 1

    assert (
        client.post(f"/api/audio-jobs/{third_job_id}/cancel").json()["status"]
        == "cancelled"
    )

    release_first_job.set()
    assert wait_for_job_status(first_job_id, {"done"})["status"] == "done"
    assert wait_for_job_status(second_job_id, {"cancelled"})["status"] == "cancelled"
    assert wait_for_job_status(third_job_id, {"cancelled"})["status"] == "cancelled"

    assert generated_texts == ["First job"]


def test_running_audio_job_cancels_at_generation_checkpoint(monkeypatch):

    generation_started = Event()
    release_generation = Event()

    def fake_generate_audio_file(
        text: str,
        language_code: str,
        voice: str,
        output_id: str,
        progress_callback=None,
    ) -> str:

        generation_started.set()

        assert release_generation.wait(timeout=3)

        file_name = f"{output_id}.wav"
        (AUDIO_DIR / file_name).write_bytes(b"cancelled-wave-data")
        return file_name

    monkeypatch.setattr("app.main.generate_audio_file", fake_generate_audio_file)

    create_response = client.post(
        "/api/audio-jobs",
        json={"text": "Cancel running", "language_code": "a", "summarize": False},
    )
    job_id = create_response.json()["job_id"]
    assert generation_started.wait(timeout=3)

    cancel_response = client.post(f"/api/audio-jobs/{job_id}/cancel")
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancel_requested"

    release_generation.set()
    cancelled_job = wait_for_job_status(job_id, {"cancelled"})

    assert cancelled_job["audio_url"] is None
    from app import main

    assert main.audio_storage.exists(f"{job_id}.wav") is False


def test_cancel_audio_job_returns_not_found():

    response = client.post("/api/audio-jobs/missing/cancel")

    assert response.status_code == 404
    assert response.json()["detail"] == "Audio job not found"


def test_audio_file_redirects_to_presigned_minio_url(monkeypatch):

    from app import main

    class FakeRemoteStorage:
        def exists(self, object_key: str) -> bool:
            assert object_key == "job123.wav"
            return True

        def presigned_get_url(
            self,
            object_key: str,
            download_filename: str | None = None,
        ) -> str:
            assert object_key == "job123.wav"
            assert download_filename is None
            return "http://127.0.0.1:9000/audio/job123.wav?signed=true"

        def local_path(self, object_key: str):
            raise AssertionError("Remote storage must use the presigned URL")

    monkeypatch.setattr(main, "audio_storage", FakeRemoteStorage())

    response = client.get(
        "/api/audio-files/job123.wav",
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"] == (
        "http://127.0.0.1:9000/audio/job123.wav?signed=true"
    )
