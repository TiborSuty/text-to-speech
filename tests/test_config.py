from app.config import (
    DEFAULT_AUDIO_RETENTION_HOURS,
    AppSettings,
)


def test_settings_read_audio_retention_from_environment(monkeypatch):
    monkeypatch.setenv("AUDIO_RETENTION_HOURS", "12.5")

    settings = AppSettings.from_environment()

    assert settings.audio_retention_hours == 12.5


def test_settings_use_default_for_invalid_audio_retention(monkeypatch):
    monkeypatch.setenv("AUDIO_RETENTION_HOURS", "invalid")

    settings = AppSettings.from_environment()

    assert settings.audio_retention_hours == DEFAULT_AUDIO_RETENTION_HOURS
