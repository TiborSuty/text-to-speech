# Imports FastAPI's synchronous test client for endpoint tests.
from fastapi.testclient import TestClient

# Imports the FastAPI app instance under test.
from app.main import app
# Imports the summarization exception used to test local model failures.
from app.text import SummarizationError

# Creates a reusable client that sends requests to the in-process app.
client = TestClient(app)


# Verifies that the health endpoint reports the API as running.
def test_health_endpoint_returns_ok():
    # Sends a GET request to the health-check endpoint.
    response = client.get("/api/health")

    # Confirms the endpoint returns a successful HTTP status.
    assert response.status_code == 200
    # Confirms the endpoint returns the expected health payload.
    assert response.json() == {"status": "ok"}


# Verifies that the languages endpoint returns supported language data.
def test_languages_endpoint_returns_supported_languages():
    # Sends a GET request to the language-list endpoint.
    response = client.get("/api/languages")

    # Confirms the endpoint returns a successful HTTP status.
    assert response.status_code == 200
    # Parses the JSON response into a Python value for assertions.
    languages = response.json()
    # Confirms the first language uses the default American English code.
    assert languages[0]["code"] == "a"
    # Confirms the first language label names American English.
    assert "American English" in languages[0]["label"]


# Verifies that blank input text is rejected before audio generation.
def test_create_audio_rejects_blank_text():
    # Sends a POST request with whitespace-only text.
    response = client.post(
        # Targets the audio-generation endpoint.
        "/api/audio",
        # Provides a request body that should fail text validation.
        json={"text": "   ", "language_code": "a", "summarize": False},
    )

    # Confirms FastAPI/Pydantic rejects the invalid request.
    assert response.status_code == 422


# Verifies that unsupported language codes are rejected.
def test_create_audio_rejects_unsupported_language_code():
    # Sends a POST request with a language code outside the supported set.
    response = client.post(
        # Targets the audio-generation endpoint.
        "/api/audio",
        # Provides a request body with an invalid language code.
        json={"text": "Hello", "language_code": "xx", "summarize": False},
    )

    # Confirms the endpoint rejects the unsupported language.
    assert response.status_code == 422
    # Confirms the endpoint returns the expected error detail.
    assert response.json()["detail"] == "Unsupported language code"


# Verifies that successful audio generation returns the generated audio URL.
def test_create_audio_returns_audio_url(monkeypatch):
    # Defines a fake audio generator so the test does not run Kokoro.
    def fake_generate_audio_file(text: str, language_code: str) -> str:
        # Confirms the endpoint passes through the submitted text.
        assert text == "Hello world"
        # Confirms the endpoint passes through the selected language code.
        assert language_code == "a"
        # Returns the file name that the endpoint should expose.
        return "audio.wav"

    # Replaces the real audio generator with the fake test implementation.
    monkeypatch.setattr("app.main.generate_audio_file", fake_generate_audio_file)

    # Sends a valid audio-generation request without summarization.
    response = client.post(
        # Targets the audio-generation endpoint.
        "/api/audio",
        # Provides the request body expected to succeed.
        json={"text": "Hello world", "language_code": "a", "summarize": False},
    )

    # Confirms the endpoint returns a successful HTTP status.
    assert response.status_code == 200
    # Confirms the endpoint returns the generated audio URL and no summary.
    assert response.json() == {
        # Confirms the API prefixes the file name with the mounted audio path.
        "audio_url": "/audios/audio.wav",
        # Confirms no summary is returned when summarization is disabled.
        "summarized_text": None,
    }


# Verifies that summarized text is used for audio when requested.
def test_create_audio_returns_summary_when_requested(monkeypatch):
    # Defines a fake summarizer so the test does not call the language model.
    def fake_summarize_text(text: str) -> str:
        # Confirms the endpoint passes the original submitted text to the summarizer.
        assert text == "Long text"
        # Returns the summary that should be sent to audio generation.
        return "Short summary."

    # Defines a fake audio generator so the test does not run Kokoro.
    def fake_generate_audio_file(text: str, language_code: str) -> str:
        # Confirms audio generation receives the summarized text.
        assert text == "Short summary."
        # Confirms the selected language code is preserved.
        assert language_code == "a"
        # Returns the file name that the endpoint should expose.
        return "audio.wav"

    # Replaces the real summarizer with the fake test implementation.
    monkeypatch.setattr("app.main.summarize_text", fake_summarize_text)
    # Replaces the real audio generator with the fake test implementation.
    monkeypatch.setattr("app.main.generate_audio_file", fake_generate_audio_file)

    # Sends a valid audio-generation request with summarization enabled.
    response = client.post(
        # Targets the audio-generation endpoint.
        "/api/audio",
        # Provides the request body expected to summarize before audio generation.
        json={"text": "Long text", "language_code": "a", "summarize": True},
    )

    # Confirms the endpoint returns a successful HTTP status.
    assert response.status_code == 200
    # Confirms the endpoint returns both the audio URL and generated summary.
    assert response.json() == {
        # Confirms the API prefixes the file name with the mounted audio path.
        "audio_url": "/audios/audio.wav",
        # Confirms the summary is included in the response.
        "summarized_text": "Short summary.",
    }


# Verifies that local summarizer failures return an actionable API error.
def test_create_audio_reports_summarizer_unavailable(monkeypatch):
    # Defines the message the backend should return when Ollama is unavailable.
    error_message = (
        # Explains that the local Ollama summarization dependency needs setup.
        "Could not summarize text. Make sure Ollama is running and deepseek-r1:8b is installed."
    )

    # Defines a fake summarizer that simulates an Ollama or model failure.
    def fake_summarize_text(text: str) -> str:
        # Confirms the endpoint still passes the original text into summarization.
        assert text == "Long text"
        # Raises the app-specific summarization failure.
        raise SummarizationError(error_message)

    # Replaces the real summarizer with the failing test implementation.
    monkeypatch.setattr("app.main.summarize_text", fake_summarize_text)

    # Sends a request that requires summarization before audio generation.
    response = client.post(
        # Targets the audio-generation endpoint.
        "/api/audio",
        # Provides a valid body with summarization enabled.
        json={"text": "Long text", "language_code": "a", "summarize": True},
    )

    # Confirms the endpoint reports an unavailable local dependency.
    assert response.status_code == 503
    # Confirms the response includes the actionable Ollama setup message.
    assert response.json()["detail"] == error_message


# Verifies that the async audio job endpoint returns a job ID.
def test_create_audio_job_returns_job_id(monkeypatch):
    # Defines a fake audio generator so the background task does not run Kokoro.
    def fake_generate_audio_file(text: str, language_code: str) -> str:
        # Confirms the async endpoint passes through the submitted text.
        assert text == "Hello world"
        # Confirms the async endpoint passes through the selected language code.
        assert language_code == "a"
        # Returns the file name that the job should expose.
        return "audio.wav"

    # Replaces the real audio generator with the fake test implementation.
    monkeypatch.setattr("app.main.generate_audio_file", fake_generate_audio_file)

    # Sends a valid async audio-generation request.
    response = client.post(
        # Targets the async audio-job creation endpoint.
        "/api/audio-jobs",
        # Provides the request body expected to succeed.
        json={"text": "Hello world", "language_code": "a", "summarize": False},
    )

    # Confirms the endpoint accepted the job instead of blocking for a sync response.
    assert response.status_code == 202
    # Extracts the generated job ID from the response body.
    job_id = response.json()["job_id"]
    # Confirms the job ID is a non-empty string.
    assert isinstance(job_id, str)
    # Confirms the job ID has content.
    assert job_id


# Verifies that async audio job status reports completion data.
def test_audio_job_status_returns_completed_job(monkeypatch):
    # Defines a fake audio generator so the background task does not run Kokoro.
    def fake_generate_audio_file(text: str, language_code: str) -> str:
        # Confirms the job receives the original submitted text.
        assert text == "Hello world"
        # Confirms the job receives the selected language code.
        assert language_code == "a"
        # Returns the generated audio file name.
        return "audio.wav"

    # Replaces the real audio generator with the fake test implementation.
    monkeypatch.setattr("app.main.generate_audio_file", fake_generate_audio_file)

    # Creates an async audio job.
    create_response = client.post(
        # Targets the async audio-job creation endpoint.
        "/api/audio-jobs",
        # Provides a request body that should complete successfully.
        json={"text": "Hello world", "language_code": "a", "summarize": False},
    )
    # Extracts the created job ID.
    job_id = create_response.json()["job_id"]

    # Requests the current job status.
    status_response = client.get(f"/api/audio-jobs/{job_id}")

    # Confirms the status endpoint succeeds.
    assert status_response.status_code == 200
    # Confirms the completed job payload contains the final audio URL.
    assert status_response.json() == {
        # Confirms the response belongs to the created job.
        "job_id": job_id,
        # Confirms the job reached the done state.
        "status": "done",
        # Confirms the audio URL matches the generated file.
        "audio_url": "/audios/audio.wav",
        # Confirms no summary is returned when summarization is disabled.
        "summarized_text": None,
        # Confirms no error is returned for a successful job.
        "error": None,
    }


# Verifies that async audio jobs can stream a terminal Server-Sent Event.
def test_audio_job_events_stream_done_event(monkeypatch):
    # Defines a fake audio generator so the background task does not run Kokoro.
    def fake_generate_audio_file(text: str, language_code: str) -> str:
        # Confirms the job receives the original submitted text.
        assert text == "Hello world"
        # Confirms the job receives the selected language code.
        assert language_code == "a"
        # Returns the generated audio file name.
        return "audio.wav"

    # Replaces the real audio generator with the fake test implementation.
    monkeypatch.setattr("app.main.generate_audio_file", fake_generate_audio_file)

    # Creates an async audio job.
    create_response = client.post(
        # Targets the async audio-job creation endpoint.
        "/api/audio-jobs",
        # Provides a request body that should complete successfully.
        json={"text": "Hello world", "language_code": "a", "summarize": False},
    )
    # Extracts the created job ID.
    job_id = create_response.json()["job_id"]

    # Opens the SSE endpoint for the created job.
    with client.stream("GET", f"/api/audio-jobs/{job_id}/events") as stream_response:
        # Confirms the endpoint returns a successful streaming response.
        assert stream_response.status_code == 200
        # Reads all events until the stream closes after the done event.
        stream_text = "".join(stream_response.iter_text())

    # Confirms the stream uses SSE data messages.
    assert "data: " in stream_text
    # Confirms the terminal done status was streamed.
    assert '"status":"done"' in stream_text
    # Confirms the generated audio URL was streamed.
    assert '"audio_url":"/audios/audio.wav"' in stream_text


# Verifies that async summarizer failures stream a failed job state.
def test_audio_job_events_stream_failed_summary_event(monkeypatch):
    # Defines the message the backend should return when Ollama is unavailable.
    error_message = (
        # Explains that the local Ollama summarization dependency needs setup.
        "Could not summarize text. Make sure Ollama is running and deepseek-r1:8b is installed."
    )

    # Defines a fake summarizer that simulates an Ollama or model failure.
    def fake_summarize_text(text: str) -> str:
        # Confirms the endpoint still passes the original text into summarization.
        assert text == "Long text"
        # Raises the app-specific summarization failure.
        raise SummarizationError(error_message)

    # Replaces the real summarizer with the failing test implementation.
    monkeypatch.setattr("app.main.summarize_text", fake_summarize_text)

    # Creates an async audio job that requires summarization.
    create_response = client.post(
        # Targets the async audio-job creation endpoint.
        "/api/audio-jobs",
        # Provides a valid body with summarization enabled.
        json={"text": "Long text", "language_code": "a", "summarize": True},
    )
    # Extracts the created job ID.
    job_id = create_response.json()["job_id"]

    # Opens the SSE endpoint for the created job.
    with client.stream("GET", f"/api/audio-jobs/{job_id}/events") as stream_response:
        # Confirms the endpoint returns a successful streaming response.
        assert stream_response.status_code == 200
        # Reads all events until the stream closes after the failed event.
        stream_text = "".join(stream_response.iter_text())

    # Confirms the terminal failed status was streamed.
    assert '"status":"failed"' in stream_text
    # Confirms the actionable summarizer error was streamed.
    assert error_message in stream_text
