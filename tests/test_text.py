from app.models import PodcastScriptRequest, PodcastScriptResponse
from app.text import clean_text, create_podcast_script


def test_clean_text_removes_think_blocks_and_trims_whitespace():

    text = "\n  <think>hidden reasoning</think>\n  Final summary.  \n"

    result = clean_text(text)

    assert result == "Final summary."


def test_clean_text_preserves_text_without_think_blocks():

    assert clean_text("  Keep this text.  ") == "Keep this text."


def test_create_podcast_script_uses_structured_output(monkeypatch):

    calls: dict[str, object] = {}

    class FakeStructuredModel:
        def invoke(self, prompt: str) -> PodcastScriptResponse:
            calls["prompt"] = prompt
            return PodcastScriptResponse(
                title="A useful episode",
                segments=[
                    {"speaker": "guest", "text": "The source explained SQLite."},
                ],
            )

    class FakeChatOllama:
        def __init__(self, **kwargs):
            calls["model_kwargs"] = kwargs

        def with_structured_output(self, schema, method: str):
            calls["schema"] = schema
            calls["method"] = method
            return FakeStructuredModel()

    monkeypatch.setattr("app.text.ChatOllama", FakeChatOllama)

    result = create_podcast_script(
        PodcastScriptRequest(
            text="SQLite is an embedded database.",
            format="narration",
            duration="short",
        )
    )

    assert calls["schema"] is PodcastScriptResponse
    assert calls["method"] == "json_schema"

    assert "Format: narration" in str(calls["prompt"])
    assert "SQLite is an embedded database." in str(calls["prompt"])

    assert result.segments[0].speaker == "host"
