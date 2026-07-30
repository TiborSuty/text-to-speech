import os

from dataclasses import dataclass


DEFAULT_AUDIO_RETENTION_HOURS = 168.0


def get_audio_retention_hours() -> float:
    try:
        return float(
            os.getenv(
                "AUDIO_RETENTION_HOURS",
                str(DEFAULT_AUDIO_RETENTION_HOURS),
            )
        )
    except ValueError:
        return DEFAULT_AUDIO_RETENTION_HOURS


@dataclass(frozen=True)
class AppSettings:
    name: str = "AI Podcaster API"
    version: str = "0.1.0"
    cors_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    )
    audio_retention_hours: float = DEFAULT_AUDIO_RETENTION_HOURS

    @classmethod
    def from_environment(cls) -> "AppSettings":
        return cls(audio_retention_hours=get_audio_retention_hours())


settings = AppSettings.from_environment()
