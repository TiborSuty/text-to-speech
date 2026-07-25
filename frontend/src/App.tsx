import { FormEvent, useEffect, useMemo, useState } from 'react';

import './App.css';
import { buildAudioUrl, fetchLanguages, generateAudio } from './api';
import type { LanguageOption } from './types';

function getInitialLanguage(languages: LanguageOption[]): string {
  return languages.find((language) => language.code === 'a')?.code ?? languages[0]?.code ?? '';
}

export default function App() {
  const [languages, setLanguages] = useState<LanguageOption[]>([]);
  const [languageCode, setLanguageCode] = useState('');
  const [text, setText] = useState('');
  const [summarize, setSummarize] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [summarizedText, setSummarizedText] = useState<string | null>(null);
  const [isLoadingLanguages, setIsLoadingLanguages] = useState(true);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const trimmedText = text.trim();
  const canGenerate = Boolean(trimmedText) && Boolean(languageCode) && !isGenerating;
  const resolvedAudioUrl = useMemo(
    () => (audioUrl ? buildAudioUrl(audioUrl) : null),
    [audioUrl],
  );

  useEffect(() => {
    let isMounted = true;

    async function loadLanguages() {
      try {
        const options = await fetchLanguages();
        if (!isMounted) {
          return;
        }

        setLanguages(options);
        setLanguageCode(getInitialLanguage(options));
      } catch (loadError) {
        if (!isMounted) {
          return;
        }

        setError(
          loadError instanceof Error
            ? loadError.message
            : 'Could not load supported languages',
        );
      } finally {
        if (isMounted) {
          setIsLoadingLanguages(false);
        }
      }
    }

    loadLanguages();

    return () => {
      isMounted = false;
    };
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!canGenerate) {
      return;
    }

    setIsGenerating(true);
    setError(null);
    setAudioUrl(null);
    setSummarizedText(null);

    try {
      const response = await generateAudio({
        text: trimmedText,
        language_code: languageCode,
        summarize,
      });

      setAudioUrl(response.audio_url);
      setSummarizedText(response.summarized_text);
    } catch (generateError) {
      setError(
        generateError instanceof Error
          ? generateError.message
          : 'Could not generate audio',
      );
    } finally {
      setIsGenerating(false);
    }
  }

  return (
    <main className="app-shell">
      <section className="tool-panel" aria-labelledby="app-title">
        <div className="title-block">
          <p className="eyebrow">Text to speech</p>
          <h1 id="app-title">AI Podcaster</h1>
        </div>

        <form className="generator-form" onSubmit={handleSubmit}>
          <label className="field">
            <span>Select a language</span>
            <select
              value={languageCode}
              onChange={(event) => setLanguageCode(event.target.value)}
              disabled={isLoadingLanguages || isGenerating}
            >
              {languages.map((language) => (
                <option key={language.code} value={language.code}>
                  {language.label}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>Enter text</span>
            <textarea
              value={text}
              onChange={(event) => setText(event.target.value)}
              rows={10}
              disabled={isGenerating}
            />
          </label>

          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={summarize}
              onChange={(event) => setSummarize(event.target.checked)}
              disabled={isGenerating}
            />
            <span>Summarize text</span>
          </label>

          <button type="submit" disabled={!canGenerate}>
            {isGenerating ? 'Generating...' : 'Generate Audio'}
          </button>
        </form>

        {error ? (
          <p className="error-message" role="alert">
            {error}
          </p>
        ) : null}

        {resolvedAudioUrl ? (
          <section className="result-panel" aria-label="Generated result">
            <audio aria-label="Generated audio" controls src={resolvedAudioUrl} />

            {summarizedText ? (
              <div className="summary-panel">
                <h2>Generated text</h2>
                <p>{summarizedText}</p>
              </div>
            ) : null}
          </section>
        ) : null}
      </section>
    </main>
  );
}
