# Imports Literal so job status values stay restricted to known strings.
from typing import Literal

# Imports Pydantic helpers for request validation and response serialization.
from pydantic import BaseModel, Field, field_validator


# Defines every lifecycle state an asynchronous audio job can report.
AudioJobStatus = Literal["queued", "summarizing", "generating", "done", "failed"]


# Describes the JSON returned by the health-check endpoint.
class HealthResponse(BaseModel):
    # Stores the service status string, such as "ok".
    status: str


# Describes one language option returned to the frontend.
class LanguageOption(BaseModel):
    # Stores the human-readable language label shown in the dropdown.
    label: str
    # Stores the Kokoro language code submitted back to the API.
    code: str


# Describes and validates the JSON body sent to the audio endpoint.
class AudioRequest(BaseModel):
    # Stores the text to summarize or convert to speech, requiring at least one character.
    text: str = Field(min_length=1)
    # Stores the requested Kokoro language code, requiring at least one character.
    language_code: str = Field(min_length=1)
    # Controls whether the API summarizes the text before generating speech.
    summarize: bool = False

    # Registers custom validation for the text field.
    @field_validator("text")
    # Allows Pydantic to call this validator on the model class.
    @classmethod
    # Rejects values that are only whitespace after trimming.
    def text_must_not_be_blank(cls, value: str) -> str:
        # Removes surrounding whitespace from the submitted text.
        stripped_value = value.strip()
        # Checks whether anything remains after whitespace is removed.
        if not stripped_value:
            # Reports a validation error that FastAPI converts into a 422 response.
            raise ValueError("Text is required")
        # Returns the trimmed text so downstream code receives clean input.
        return stripped_value


# Describes the JSON returned after audio generation succeeds.
class AudioResponse(BaseModel):
    # Stores the URL path where the generated audio file can be downloaded or played.
    audio_url: str
    # Stores the generated summary, or None when summarization was not requested.
    summarized_text: str | None = None


# Describes the JSON returned immediately after an async audio job is created.
class AudioJobCreateResponse(BaseModel):
    # Stores the unique ID the frontend uses to subscribe to job progress events.
    job_id: str


# Describes one async audio job status payload.
class AudioJobStatusResponse(BaseModel):
    # Stores the unique job ID this status belongs to.
    job_id: str
    # Stores the current lifecycle state for the job.
    status: AudioJobStatus
    # Stores the generated audio URL once the job completes.
    audio_url: str | None = None
    # Stores the optional summary once the job completes.
    summarized_text: str | None = None
    # Stores a user-visible error message when the job fails.
    error: str | None = None
