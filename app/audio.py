# Imports Path so the app can build filesystem paths portably.
from pathlib import Path

# Imports NumPy to combine generated audio chunks into one array.
import numpy as np
# Imports SoundFile to write the generated waveform as a WAV file.
import soundfile as sf
# Imports Kokoro's pipeline class, which turns text into speech audio.
from kokoro import KPipeline

# Points to the repository-level audios directory where generated files are stored.
AUDIO_DIR = Path(__file__).resolve().parent.parent / "audios"
# Uses one stable output file name so each generation replaces the previous audio.
AUDIO_FILE_NAME = "audio.wav"
# Sets the sample rate expected by the generated Kokoro audio.
AUDIO_SAMPLE_RATE = 24000
# Selects the Kokoro voice used for generated speech.
VOICE = "af_heart"


# Deletes old generated audio files before writing a new one.
def clear_audio_directory(audio_dir: Path = AUDIO_DIR) -> None:
    # Creates the audio directory if it does not already exist.
    audio_dir.mkdir(exist_ok=True)

    # Iterates over every item currently in the audio output directory.
    for file_path in audio_dir.iterdir():
        # Only removes files, leaving any nested directories untouched.
        if file_path.is_file():
            # Deletes the old audio file from disk.
            file_path.unlink()


# Generates a speech WAV file for the given text and language code.
def generate_audio_file(text: str, language_code: str) -> str:
    # Clears previous generated files so the output directory stays predictable.
    clear_audio_directory()

    # Creates a Kokoro pipeline configured for the requested language.
    pipeline = KPipeline(lang_code=language_code)
    # Starts audio generation with the selected voice.
    generator = pipeline(text, voice=VOICE)
    # Pulls just the audio arrays out of the Kokoro generator output.
    chunks = [audio for _, _, audio in generator]

    # Detects the rare case where Kokoro returns no audio chunks at all.
    if not chunks:
        # Fails loudly so the API can return an error instead of an empty file.
        raise RuntimeError("Kokoro did not generate audio")

    # Concatenates all generated audio chunks into one continuous waveform.
    full_audio = np.concatenate(chunks, axis=0)
    # Writes the waveform to disk as the stable WAV output file.
    sf.write(AUDIO_DIR / AUDIO_FILE_NAME, full_audio, AUDIO_SAMPLE_RATE)

    # Returns only the file name so the API layer can build the public URL.
    return AUDIO_FILE_NAME
