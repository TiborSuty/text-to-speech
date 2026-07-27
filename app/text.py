# Imports regular expressions for removing model thinking blocks from output.
import re
# Imports os so the Ollama endpoint and model can be configured for Docker.
import os

# Imports LangChain's template helper for building the summarization prompt.
from langchain_core.prompts import ChatPromptTemplate
# Imports the Ollama chat model wrapper used to call the local model.
from langchain_ollama import ChatOllama

# Defines the prompt template sent to the summarization model.
SUMMARY_TEMPLATE = """
Summarize the following text by highlighting the key points.
Maintain a conversational tone and keep the summary easy to follow for a general audience.
Text: {text}
"""

# Stores the Ollama HTTP base URL used by LangChain.
OLLAMA_BASE_URL = (
    # Prefers the app-specific base URL used by Docker Compose.
    os.getenv("OLLAMA_BASE_URL")
    # Falls back to Ollama's own host environment variable when present.
    or os.getenv("OLLAMA_HOST")
    # Defaults to a local Ollama process for non-Docker development.
    or "http://127.0.0.1:11434"
)
# Stores the default Ollama model used for summarization.
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "deepseek-r1:8b")


# Defines the error raised when local Ollama summarization cannot complete.
class SummarizationError(RuntimeError):
    # Gives the app a specific exception type for summarization failures.
    pass


# Removes hidden reasoning tags and surrounding whitespace from model output.
def clean_text(text: str) -> str:
    # Deletes any <think>...</think> block, including multi-line content.
    cleaned_text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Trims leading and trailing whitespace from the cleaned response.
    return cleaned_text.strip()


# Summarizes text with a local Ollama model before sending it to text-to-speech.
def summarize_text(text: str, model_name: str = OLLAMA_MODEL) -> str:
    # Converts the plain template string into a reusable LangChain prompt.
    prompt = ChatPromptTemplate.from_template(SUMMARY_TEMPLATE)
    # Connects the prompt to the selected Ollama chat model.
    chain = prompt | ChatOllama(model=model_name, base_url=OLLAMA_BASE_URL)

    # Converts Ollama/model failures into an app-specific exception.
    try:
        # Invokes the prompt/model chain with the user's text.
        summary = chain.invoke({"text": text})
    # Handles connection errors, missing models, and other local model failures.
    except Exception as exc:
        # Raises a stable message the API can safely return to the frontend.
        raise SummarizationError(
            # Explains the most common local setup problem behind summarization failures.
            f"Could not summarize text. Make sure Ollama is running and {model_name} is installed."
        # Preserves the original exception for backend debugging.
        ) from exc
    # Returns the model content after removing hidden reasoning markup.
    return clean_text(summary.content)
