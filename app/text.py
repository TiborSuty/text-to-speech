import re

from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

SUMMARY_TEMPLATE = """
Summarize the following text by highlighting the key points.
Maintain a conversational tone and keep the summary easy to follow for a general audience.
Text: {text}
"""


def clean_text(text: str) -> str:
    cleaned_text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return cleaned_text.strip()


def summarize_text(text: str, model_name: str = "deepseek-r1:8b") -> str:
    prompt = ChatPromptTemplate.from_template(SUMMARY_TEMPLATE)
    chain = prompt | ChatOllama(model=model_name)

    summary = chain.invoke({"text": text})
    return clean_text(summary.content)
