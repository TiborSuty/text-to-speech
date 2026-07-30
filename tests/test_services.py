from app.config import AppSettings
from app.main import create_app
from app.models import AudioRequest
from app.services.audio_generation import AudioGenerationService


def test_audio_generation_service_prepares_summary():
    service = AudioGenerationService(
        summarize_text=lambda text: f"Summary: {text}",
        generate_audio_file=lambda *_args, **_kwargs: "unused.wav",
        generate_segmented_audio_file=lambda *_args, **_kwargs: "unused.wav",
    )
    request = AudioRequest(
        text="Long source",
        language_code="a",
        summarize=True,
    )

    prepared = service.prepare(request)

    assert prepared.text == "Summary: Long source"
    assert prepared.summarized_text == "Summary: Long source"


def test_audio_generation_service_renders_requested_format():
    received_options = {}

    def generate_audio_file(
        text,
        language_code,
        voice,
        **options,
    ):
        received_options.update(options)
        assert text == "Short source"
        assert language_code == "a"
        assert voice == "af_heart"
        return "episode.flac"

    service = AudioGenerationService(
        summarize_text=lambda text: text,
        generate_audio_file=generate_audio_file,
        generate_segmented_audio_file=lambda *_args, **_kwargs: "unused.wav",
    )
    request = AudioRequest(
        text="Short source",
        language_code="a",
        audio_format="flac",
    )

    file_name = service.render(
        request,
        "af_heart",
        output_id="episode",
    )

    assert file_name == "episode.flac"
    assert received_options == {
        "output_id": "episode",
        "audio_format": "flac",
    }


def test_audio_generation_service_configures_segmented_rendering():
    received = {}

    def generate_segmented_audio_file(
        segments,
        language_code,
        config,
    ):
        received["segments"] = segments
        received["language_code"] = language_code
        received["config"] = config
        return "podcast.ogg"

    service = AudioGenerationService(
        summarize_text=lambda text: text,
        generate_audio_file=lambda *_args, **_kwargs: "unused.wav",
        generate_segmented_audio_file=generate_segmented_audio_file,
    )
    request = AudioRequest(
        text="Host\nGuest",
        language_code="a",
        audio_format="ogg",
        segments=[
            {
                "speaker": "host",
                "text": "Host",
                "voice": "af_heart",
            },
            {
                "speaker": "guest",
                "text": "Guest",
                "voice": "am_adam",
            },
        ],
    )

    def progress_callback(_progress):
        return True

    file_name = service.render(
        request,
        "af_heart",
        output_id="podcast",
        progress_callback=progress_callback,
    )

    assert file_name == "podcast.ogg"
    assert received["segments"] == [
        ("Host", "af_heart"),
        ("Guest", "am_adam"),
    ]
    assert received["language_code"] == "a"
    assert received["config"].output_id == "podcast"
    assert received["config"].progress_callback is progress_callback
    assert received["config"].audio_format == "ogg"


def test_create_app_uses_supplied_settings_and_api_router():
    application = create_app(
        AppSettings(
            name="Test Podcaster",
            version="9.8.7",
            cors_origins=("https://example.test",),
        )
    )

    assert application.title == "Test Podcaster"
    assert application.version == "9.8.7"
    assert "/api/health" in application.openapi()["paths"]
