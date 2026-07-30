from collections.abc import Callable
from dataclasses import dataclass

from app.models import AudioRequest


AudioGenerator = Callable[..., str]
ProgressCallback = Callable[[int], bool]
Summarizer = Callable[[str], str]


@dataclass(frozen=True)
class PreparedAudio:
    text: str
    summarized_text: str | None


@dataclass(frozen=True)
class AudioGenerationService:
    summarize_text: Summarizer
    generate_audio_file: AudioGenerator
    generate_segmented_audio_file: AudioGenerator

    def prepare(self, request: AudioRequest) -> PreparedAudio:
        if not request.summarize:
            return PreparedAudio(text=request.text, summarized_text=None)

        summarized_text = self.summarize_text(request.text)
        return PreparedAudio(
            text=summarized_text,
            summarized_text=summarized_text,
        )

    def render(
        self,
        request: AudioRequest,
        voice: str,
        *,
        text: str | None = None,
        output_id: str | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> str:
        audio_format_options = (
            {}
            if request.audio_format == "wav"
            else {"audio_format": request.audio_format}
        )
        output_options = (
            {} if output_id is None else {"output_id": output_id}
        )
        progress_options = (
            {}
            if progress_callback is None
            else {"progress_callback": progress_callback}
        )

        if request.segments:
            return self.generate_segmented_audio_file(
                [(segment.text, segment.voice) for segment in request.segments],
                request.language_code,
                **output_options,
                **progress_options,
                **audio_format_options,
            )

        return self.generate_audio_file(
            text if text is not None else request.text,
            request.language_code,
            voice,
            **output_options,
            **progress_options,
            **audio_format_options,
        )
