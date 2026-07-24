import re
from pathlib import Path

import numpy as np
import soundfile as sf
import streamlit as st
from kokoro import KPipeline
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

audios_directory = Path(__file__).parent / "audios"

supported_languages = {
    "🇺🇸 American English": "a",
    "🇬🇧 British English": "b",
    "🇪🇸 Spanish": "e",
    "🇫🇷 French": "f",
    "🇮🇳 Hindi": "h",
    "🇮🇹 Italian": "i",
    "🇯🇵 Japanese": "j",
    "🇧🇷 Brazilian Portuguese": "p",
    "🇨🇳 Mandarin Chinese": "z",
}

summary_template = """
Summarize the following text by highlighting the key points.
Maintain a conversational tone and keep the summary easy to follow for a general audience.
Text: {text}
"""

model = ChatOllama(model="deepseek-r1:8b")


def generate_audio(pipeline, text):
    audios_directory.mkdir(exist_ok=True)

    for file in audios_directory.iterdir():
        if file.is_file():
            file.unlink()

    generator = pipeline(text, voice="af_heart")
    chunks = []

    for i, (gs, ps, audio) in enumerate(generator):
        chunks.append(audio)

    file_name = "audio.wav"
    full_audio = np.concatenate(chunks, axis=0)
    sf.write(audios_directory / file_name, full_audio, 24000)

    return file_name


def summarize_text(text):
    prompt = ChatPromptTemplate.from_template(summary_template)
    chain = prompt | model

    summary = chain.invoke({"text": text})
    return clean_text(summary.content)


def clean_text(text):
    cleaned_text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return cleaned_text.strip()


st.title("AI Podcaster")

language = st.selectbox("Select a language:", list(supported_languages.keys()), index=0)
text = st.text_area("Enter text to generate audio:")
should_summarize = st.checkbox("Summarize text")
button = st.button("Generate Audio")

if button and text:
    pipeline = KPipeline(lang_code=supported_languages[language])

    if should_summarize:
        text = summarize_text(text)

    file_name = generate_audio(pipeline, text)
    st.audio(str(audios_directory / file_name))
