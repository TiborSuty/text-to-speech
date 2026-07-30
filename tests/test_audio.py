import numpy as np

import pytest


from app import audio


def test_generate_audio_file_keeps_unique_job_outputs(monkeypatch, tmp_path):

    class FakePipeline:
        def __init__(self, lang_code: str):

            assert lang_code == "a"

        def __call__(self, text: str, voice: str):

            assert text == "Hello"
            assert voice == "af_heart"

            yield "He", None, np.array([0.1, 0.2], dtype=np.float32)
            yield "llo", None, np.array([0.3], dtype=np.float32)

    monkeypatch.setattr(audio, "AUDIO_DIR", tmp_path)

    monkeypatch.setattr(audio, "KPipeline", FakePipeline)

    first_file = audio.generate_audio_file("Hello", "a", "af_heart", "job123")
    second_file = audio.generate_audio_file("Hello", "a", "af_heart", "job456")

    assert first_file == "job123.wav"
    assert second_file == "job456.wav"

    assert (tmp_path / first_file).is_file()
    assert (tmp_path / second_file).is_file()

    waveform, sample_rate = audio.sf.read(tmp_path / first_file)
    assert sample_rate == audio.AUDIO_SAMPLE_RATE
    assert waveform == pytest.approx([0.1, 0.2, 0.3], abs=1e-4)

    assert list(tmp_path.glob(".*.tmp")) == []


def test_generate_audio_file_cancels_between_chunks(monkeypatch, tmp_path):

    class FakePipeline:
        def __init__(self, lang_code: str):
            assert lang_code == "a"

        def __call__(self, text: str, voice: str):
            assert text == "Hello"
            assert voice == "af_heart"
            yield "He", None, np.array([0.1], dtype=np.float32)
            yield "llo", None, np.array([0.2], dtype=np.float32)

    monkeypatch.setattr(audio, "AUDIO_DIR", tmp_path)
    monkeypatch.setattr(audio, "KPipeline", FakePipeline)
    reported_progress: list[int] = []

    def progress_callback(progress: int) -> bool:
        reported_progress.append(progress)
        return len(reported_progress) < 2

    with pytest.raises(audio.AudioGenerationCancelled):
        audio.generate_audio_file(
            "Hello",
            "a",
            "af_heart",
            "canceljob",
            progress_callback=progress_callback,
        )

    assert reported_progress == [40, 99]
    assert (tmp_path / "canceljob.wav").exists() is False
    assert list(tmp_path.glob(".*.tmp")) == []


def test_generate_audio_file_rejects_unsafe_output_id():

    with pytest.raises(ValueError, match="alphanumeric"):
        audio.generate_audio_file("Hello", "a", "af_heart", "../outside")


@pytest.mark.parametrize(
    ("audio_format", "expected_extension", "expected_container"),
    [
        ("wav", "wav", "WAV"),
        ("mp3", "mp3", "MP3"),
        ("flac", "flac", "FLAC"),
        ("ogg", "ogg", "OGG"),
    ],
)
def test_generate_audio_file_supports_multiple_formats(
    monkeypatch,
    tmp_path,
    audio_format,
    expected_extension,
    expected_container,
):

    class FakePipeline:
        def __init__(self, lang_code: str):
            assert lang_code == "a"

        def __call__(self, text: str, voice: str):
            assert text == "Hello"
            assert voice == "af_heart"
            yield text, None, np.sin(
                np.linspace(0, 20 * np.pi, audio.AUDIO_SAMPLE_RATE)
            ).astype(np.float32)

    monkeypatch.setattr(audio, "AUDIO_DIR", tmp_path)
    monkeypatch.setattr(audio, "KPipeline", FakePipeline)

    file_name = audio.generate_audio_file(
        "Hello",
        "a",
        "af_heart",
        "formatjob",
        audio_format=audio_format,
    )

    assert file_name == f"formatjob.{expected_extension}"
    file_info = audio.sf.info(tmp_path / file_name)
    assert file_info.format == expected_container
    assert file_info.samplerate == audio.AUDIO_SAMPLE_RATE


def test_generate_segmented_audio_file_joins_speaker_turns(monkeypatch, tmp_path):

    rendered_segments: list[tuple[str, str]] = []

    class FakePipeline:
        def __init__(self, lang_code: str):
            assert lang_code == "a"

        def __call__(self, text: str, voice: str):
            rendered_segments.append((text, voice))
            sample = 0.1 if voice == "af_heart" else 0.2
            yield text, None, np.array([sample], dtype=np.float32)

    monkeypatch.setattr(audio, "AUDIO_DIR", tmp_path)
    monkeypatch.setattr(audio, "KPipeline", FakePipeline)

    file_name = audio.generate_segmented_audio_file(
        [
            ("Welcome", "af_heart"),
            ("Thanks", "am_adam"),
        ],
        "a",
        "podcast123",
        pause_seconds=0.01,
    )

    assert rendered_segments == [
        ("Welcome", "af_heart"),
        ("Thanks", "am_adam"),
    ]

    waveform, sample_rate = audio.sf.read(tmp_path / file_name)

    assert sample_rate == audio.AUDIO_SAMPLE_RATE

    assert waveform[0] == pytest.approx(0.1, abs=1e-4)
    assert waveform[-1] == pytest.approx(0.2, abs=1e-4)
    assert waveform[1:-1] == pytest.approx(
        np.zeros(round(audio.AUDIO_SAMPLE_RATE * 0.01)),
        abs=1e-4,
    )
