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
