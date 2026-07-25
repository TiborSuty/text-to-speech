from pathlib import Path

import numpy as np
import soundfile as sf
from kokoro import KPipeline

AUDIO_DIR = Path(__file__).resolve().parent.parent / "audios"
AUDIO_FILE_NAME = "audio.wav"
AUDIO_SAMPLE_RATE = 24000
VOICE = "af_heart"


def clear_audio_directory(audio_dir: Path = AUDIO_DIR) -> None:
    audio_dir.mkdir(exist_ok=True)

    for file_path in audio_dir.iterdir():
        if file_path.is_file():
            file_path.unlink()


def generate_audio_file(text: str, language_code: str) -> str:
    clear_audio_directory()

    pipeline = KPipeline(lang_code=language_code)
    generator = pipeline(text, voice=VOICE)
    chunks = [audio for _, _, audio in generator]

    if not chunks:
        raise RuntimeError("Kokoro did not generate audio")

    full_audio = np.concatenate(chunks, axis=0)
    sf.write(AUDIO_DIR / AUDIO_FILE_NAME, full_audio, AUDIO_SAMPLE_RATE)

    return AUDIO_FILE_NAME
