from dataclasses import dataclass
from typing import Literal, cast

AudioFormat = Literal["wav", "mp3", "flac", "ogg"]


@dataclass(frozen=True)
class AudioFormatSpec:
    extension: str
    soundfile_format: str
    soundfile_subtype: str
    media_type: str


AUDIO_FORMAT_SPECS: dict[AudioFormat, AudioFormatSpec] = {
    "wav": AudioFormatSpec(
        extension="wav",
        soundfile_format="WAV",
        soundfile_subtype="PCM_16",
        media_type="audio/wav",
    ),
    "mp3": AudioFormatSpec(
        extension="mp3",
        soundfile_format="MP3",
        soundfile_subtype="MPEG_LAYER_III",
        media_type="audio/mpeg",
    ),
    "flac": AudioFormatSpec(
        extension="flac",
        soundfile_format="FLAC",
        soundfile_subtype="PCM_16",
        media_type="audio/flac",
    ),
    "ogg": AudioFormatSpec(
        extension="ogg",
        soundfile_format="OGG",
        soundfile_subtype="VORBIS",
        media_type="audio/ogg",
    ),
}


def get_audio_format_spec(audio_format: AudioFormat) -> AudioFormatSpec:
    return AUDIO_FORMAT_SPECS[audio_format]


def get_audio_format_from_file_name(file_name: str) -> AudioFormat:
    extension = file_name.rpartition(".")[2]

    if extension not in AUDIO_FORMAT_SPECS:
        raise ValueError("Unsupported audio file format")

    return cast(AudioFormat, extension)
