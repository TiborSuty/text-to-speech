import os
import re

from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

from app.models import PodcastScriptRequest, PodcastScriptResponse

SUMMARY_TEMPLATE = """
Summarize the following text by highlighting the key points.
Maintain a conversational tone and keep the summary easy to follow for a general audience.
Text: {text}
"""


PODCAST_SCRIPT_TEMPLATE = """
You are an experienced podcast editor. Transform the source material into a spoken
script that is accurate, natural, and easy to follow aloud.

Format: {format}
Length target: {duration_guide}

Rules:
- Preserve the source's important facts and do not invent facts.
- Write the title and spoken turns in the same language as the source.
- Write a concise, specific episode title.
- Use only the speaker labels "host" and "guest".
- For narration, use only "host".
- For interview, alternate naturally between host questions and guest answers.
- For explainer, let the host guide the topic and the guest clarify examples.
- Keep each turn focused and conversational.
- Do not add stage directions, markdown, sound effects, or speaker names to the text.

Source:
{text}
"""


PODCAST_DURATION_GUIDES = {
    "short": "4 to 6 turns and roughly 250 to 400 spoken words",
    "medium": "7 to 10 turns and roughly 500 to 800 spoken words",
    "long": "11 to 16 turns and roughly 900 to 1400 spoken words",
}


OLLAMA_BASE_URL = (
    os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_HOST") or "http://127.0.0.1:11434"
)

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "deepseek-r1:8b")


class SummarizationError(RuntimeError):
    pass


class PodcastScriptError(RuntimeError):
    pass


def clean_text(text: str) -> str:

    cleaned_text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

    return cleaned_text.strip()


def summarize_text(text: str, model_name: str = OLLAMA_MODEL) -> str:

    prompt = ChatPromptTemplate.from_template(SUMMARY_TEMPLATE)

    chain = prompt | ChatOllama(model=model_name, base_url=OLLAMA_BASE_URL)

    try:
        summary = chain.invoke({"text": text})

    except Exception as exc:
        raise SummarizationError(
            f"Could not summarize text. Make sure Ollama is running and {model_name} is installed."
        ) from exc

    return clean_text(summary.content)


def create_podcast_script(
    request: PodcastScriptRequest,
    model_name: str = OLLAMA_MODEL,
) -> PodcastScriptResponse:

    prompt = PODCAST_SCRIPT_TEMPLATE.format(
        format=request.format,
        duration_guide=PODCAST_DURATION_GUIDES[request.duration],
        text=request.text,
    )

    model = ChatOllama(
        model=model_name,
        base_url=OLLAMA_BASE_URL,
        temperature=0.2,
    )

    structured_model = model.with_structured_output(
        PodcastScriptResponse,
        method="json_schema",
    )

    try:
        generated_script = structured_model.invoke(prompt)

        script = PodcastScriptResponse.model_validate(generated_script)

    except Exception as exc:
        raise PodcastScriptError(
            f"Could not generate a podcast script. Make sure Ollama is running and {model_name} is installed."
        ) from exc

    if request.format == "narration":
        script = script.model_copy(
            update={
                "segments": [
                    segment.model_copy(update={"speaker": "host"})
                    for segment in script.segments
                ]
            }
        )

    return script
