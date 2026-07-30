import os

from datetime import datetime
from typing import Literal


from pydantic import BaseModel, Field, field_validator, model_validator

from app.audio_formats import AudioFormat


DEFAULT_AUDIO_MAX_TEXT_CHARACTERS = 50_000

MAX_AUDIO_MAX_TEXT_CHARACTERS = 1_000_000


def get_audio_max_text_characters() -> int:

    try:
        configured_limit = int(
            os.getenv(
                "AUDIO_MAX_TEXT_CHARACTERS",
                str(DEFAULT_AUDIO_MAX_TEXT_CHARACTERS),
            )
        )

    except ValueError:
        configured_limit = DEFAULT_AUDIO_MAX_TEXT_CHARACTERS

    return min(max(configured_limit, 1), MAX_AUDIO_MAX_TEXT_CHARACTERS)


AUDIO_MAX_TEXT_CHARACTERS = get_audio_max_text_characters()


AudioJobStatus = Literal[
    "queued",
    "summarizing",
    "generating",
    "cancel_requested",
    "cancelled",
    "done",
    "failed",
]


PodcastFormat = Literal["narration", "interview", "explainer"]

PodcastDuration = Literal["short", "medium", "long"]

PodcastSpeaker = Literal["host", "guest"]

PodcastWorkflowStatus = Literal["awaiting_review", "approved", "queued"]


class HealthResponse(BaseModel):
    status: str


class AppConfigResponse(BaseModel):
    max_text_characters: int


class VoiceOption(BaseModel):
    id: str

    label: str


class LanguageOption(BaseModel):
    label: str

    code: str

    default_voice: str

    voices: list[VoiceOption]


class PodcastScriptSegment(BaseModel):
    speaker: PodcastSpeaker

    text: str = Field(min_length=1, max_length=10_000)

    @field_validator("text")
    @classmethod
    def trim_text(cls, value: str) -> str:

        stripped_value = value.strip()

        if not stripped_value:
            raise ValueError("Podcast segment text is required")

        return stripped_value


class PodcastScriptRequest(BaseModel):
    text: str = Field(min_length=1, max_length=AUDIO_MAX_TEXT_CHARACTERS)

    format: PodcastFormat

    duration: PodcastDuration

    @field_validator("text")
    @classmethod
    def trim_source_text(cls, value: str) -> str:

        stripped_value = value.strip()

        if not stripped_value:
            raise ValueError("Text is required")

        return stripped_value


class PodcastScriptResponse(BaseModel):
    title: str = Field(min_length=1, max_length=160)

    segments: list[PodcastScriptSegment] = Field(min_length=1, max_length=24)

    @field_validator("title")
    @classmethod
    def trim_title(cls, value: str) -> str:

        stripped_value = value.strip()

        if not stripped_value:
            raise ValueError("Podcast title is required")

        return stripped_value


class PodcastWorkflowResponse(BaseModel):
    workflow_id: str

    status: PodcastWorkflowStatus

    script: PodcastScriptResponse

    facts: list[str]

    issues: list[str]

    revision_count: int = Field(ge=0, le=2)

    audio_job_id: str | None = None


class PodcastWorkflowApprovalRequest(BaseModel):
    script: PodcastScriptResponse

    language_code: str = Field(min_length=1)

    host_voice: str = Field(min_length=1)

    guest_voice: str = Field(min_length=1)

    audio_format: AudioFormat = "wav"

    @field_validator("language_code", "host_voice", "guest_voice")
    @classmethod
    def trim_audio_identifier(cls, value: str) -> str:

        return value.strip()


class AudioSegment(PodcastScriptSegment):
    voice: str = Field(min_length=1)

    @field_validator("voice")
    @classmethod
    def trim_segment_voice(cls, value: str) -> str:

        return value.strip()


class AudioRequest(BaseModel):
    text: str = Field(min_length=1, max_length=AUDIO_MAX_TEXT_CHARACTERS)

    language_code: str = Field(min_length=1)

    voice: str | None = Field(default=None, min_length=1)

    summarize: bool = False

    audio_format: AudioFormat = "wav"

    segments: list[AudioSegment] | None = Field(
        default=None,
        min_length=1,
        max_length=24,
    )

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:

        stripped_value = value.strip()

        if not stripped_value:
            raise ValueError("Text is required")

        return stripped_value

    @field_validator("voice")
    @classmethod
    def trim_voice(cls, value: str | None) -> str | None:

        if value is None:
            return None

        return value.strip()

    @model_validator(mode="after")
    def validate_segments(self) -> "AudioRequest":

        if self.segments is None:
            return self

        if self.summarize:
            raise ValueError("Podcast segments cannot be summarized")

        total_characters = sum(len(segment.text) for segment in self.segments)

        if total_characters > AUDIO_MAX_TEXT_CHARACTERS:
            raise ValueError("Podcast script is too long")

        return self


class AudioResponse(BaseModel):
    audio_url: str

    summarized_text: str | None = None


class AudioJobCreateResponse(BaseModel):
    job_id: str


class AudioJobStatusResponse(BaseModel):
    job_id: str

    status: AudioJobStatus

    queue_position: int | None = None

    progress: int = Field(ge=0, le=100)

    language_code: str

    voice: str

    summarize: bool

    audio_format: AudioFormat

    text_preview: str

    created_at: datetime

    updated_at: datetime

    audio_url: str | None = None

    summarized_text: str | None = None

    error: str | None = None
