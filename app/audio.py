import math

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4


import numpy as np

import soundfile as sf

from kokoro import KPipeline

from app.audio_formats import (
    AUDIO_FORMAT_SPECS,
    AudioFormat,
    get_audio_format_spec,
)


AUDIO_DIR = Path(__file__).resolve().parent.parent / "audios"

AUDIO_SAMPLE_RATE = 24000

PODCAST_SEGMENT_PAUSE_SECONDS = 0.35


class AudioGenerationCancelled(Exception):
    pass


@dataclass(frozen=True, slots=True)
class AudioGenerationConfig:
    output_id: str | None = None
    progress_callback: Callable[[int], bool] | None = None
    pause_seconds: float = PODCAST_SEGMENT_PAUSE_SECONDS
    audio_format: AudioFormat = "wav"

    def __post_init__(self) -> None:
        if not math.isfinite(self.pause_seconds) or self.pause_seconds < 0:
            raise ValueError("Audio segment pause must be a finite non-negative value")


def build_audio_file_name(
    output_id: str,
    audio_format: AudioFormat = "wav",
) -> str:

    if not output_id or not output_id.isalnum():
        raise ValueError("Audio output ID must be alphanumeric")

    return f"{output_id}.{get_audio_format_spec(audio_format).extension}"


def delete_audio_file(file_name: str, audio_dir: Path = AUDIO_DIR) -> None:

    if Path(file_name).name != file_name:
        raise ValueError("Audio file name must not contain a path")

    (audio_dir / file_name).unlink(missing_ok=True)


def delete_expired_audio_files(
    cutoff: datetime,
    audio_dir: Path = AUDIO_DIR,
) -> None:

    if not audio_dir.exists():
        return

    cutoff_timestamp = cutoff.timestamp()

    for audio_format in AUDIO_FORMAT_SPECS:
        for file_path in audio_dir.glob(f"*.{audio_format}"):
            try:
                modified_at = file_path.stat().st_mtime

            except FileNotFoundError:
                continue

            if modified_at < cutoff_timestamp:
                file_path.unlink(missing_ok=True)


def generate_audio_file(
    text: str,
    language_code: str,
    voice: str,
    output_id: str | None = None,
    progress_callback: Callable[[int], bool] | None = None,
    audio_format: AudioFormat = "wav",
) -> str:

    return generate_segmented_audio_file(
        segments=[(text, voice)],
        language_code=language_code,
        config=AudioGenerationConfig(
            output_id=output_id,
            progress_callback=progress_callback,
            pause_seconds=0,
            audio_format=audio_format,
        ),
    )


def _validate_audio_segments(
    segments: Sequence[tuple[str, str]],
) -> int:
    if not segments:
        raise ValueError("At least one non-empty audio segment is required")

    for text, voice in segments:
        if not text.strip():
            raise ValueError("Audio segment text must not be blank")

        if not voice.strip():
            raise ValueError("Audio segment voice must not be blank")

    return sum(len(text) for text, _voice in segments)


def _report_audio_progress(
    processed_characters: int,
    total_characters: int,
    last_reported_progress: int,
    progress_callback: Callable[[int], bool] | None,
) -> int:
    progress = min(
        99,
        max(1, round(processed_characters / total_characters * 100)),
    )

    if progress_callback is None or progress <= last_reported_progress:
        return last_reported_progress

    if not progress_callback(progress):
        raise AudioGenerationCancelled

    return progress


def generate_segmented_audio_file(
    segments: Sequence[tuple[str, str]],
    language_code: str,
    config: AudioGenerationConfig | None = None,
) -> str:

    resolved_config = config or AudioGenerationConfig()

    total_characters = _validate_audio_segments(segments)

    resolved_output_id = resolved_config.output_id or uuid4().hex

    format_spec = get_audio_format_spec(resolved_config.audio_format)

    file_name = build_audio_file_name(
        resolved_output_id,
        resolved_config.audio_format,
    )

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    output_path = AUDIO_DIR / file_name

    temporary_path = AUDIO_DIR / f".{file_name}.tmp"

    pipeline = KPipeline(lang_code=language_code)

    processed_characters = 0

    last_reported_progress = 0

    generated_audio = False

    try:
        with sf.SoundFile(
            temporary_path,
            mode="w",
            samplerate=AUDIO_SAMPLE_RATE,
            channels=1,
            format=format_spec.soundfile_format,
            subtype=format_spec.soundfile_subtype,
        ) as output_file:
            for text, voice in segments:
                generator = pipeline(text, voice=voice)
                segment_started = False

                for generated_text, _phonemes, chunk_audio in generator:
                    audio_chunk = np.asarray(chunk_audio).reshape(-1)

                    if audio_chunk.size == 0:
                        continue

                    if isinstance(generated_text, str):
                        processed_characters += len(generated_text)

                    last_reported_progress = _report_audio_progress(
                        processed_characters,
                        total_characters,
                        last_reported_progress,
                        resolved_config.progress_callback,
                    )

                    if (
                        not segment_started
                        and generated_audio
                        and resolved_config.pause_seconds > 0
                    ):
                        pause_sample_count = round(
                            AUDIO_SAMPLE_RATE * resolved_config.pause_seconds
                        )
                        output_file.write(
                            np.zeros(pause_sample_count, dtype=np.float32)
                        )

                    output_file.write(audio_chunk)

                    segment_started = True
                    generated_audio = True

                if not segment_started:
                    raise RuntimeError(
                        "Kokoro did not generate audio for an audio segment"
                    )

        temporary_path.replace(output_path)

    finally:
        temporary_path.unlink(missing_ok=True)

    return file_name
