from app.worker import (
    DEFAULT_AUDIO_WORKER_COUNT,
    MAX_AUDIO_WORKER_COUNT,
    get_audio_worker_count,
)


def test_audio_worker_count_is_validated(monkeypatch):

    monkeypatch.setenv("AUDIO_WORKER_COUNT", "many")
    assert get_audio_worker_count() == DEFAULT_AUDIO_WORKER_COUNT

    monkeypatch.setenv("AUDIO_WORKER_COUNT", "0")
    assert get_audio_worker_count() == 1

    monkeypatch.setenv("AUDIO_WORKER_COUNT", "999")
    assert get_audio_worker_count() == MAX_AUDIO_WORKER_COUNT
