from pydantic import BaseModel, Field, field_validator


class HealthResponse(BaseModel):
    status: str


class LanguageOption(BaseModel):
    label: str
    code: str


class AudioRequest(BaseModel):
    text: str = Field(min_length=1)
    language_code: str = Field(min_length=1)
    summarize: bool = False

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        stripped_value = value.strip()
        if not stripped_value:
            raise ValueError("Text is required")
        return stripped_value


class AudioResponse(BaseModel):
    audio_url: str
    summarized_text: str | None = None
