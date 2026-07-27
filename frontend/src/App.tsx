// Imports React hooks and the form event type used by the submit handler.
import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';

// Imports the component stylesheet.
import './App.css';
// Imports API helpers for backend communication, SSE URL creation, and audio URL resolution.
import { buildAudioJobEventsUrl, buildAudioUrl, createAudioJob, fetchLanguages } from './api';
// Imports the types used for audio job and language state.
import type { AudioJobStatus, AudioJobStatusResponse, LanguageOption } from './types';

// Picks the initial language code after the backend language list loads.
function getInitialLanguage(languages: LanguageOption[]): string {
  // Prefers American English, then falls back to the first available language, then empty state.
  return languages.find((language) => language.code === 'a')?.code ?? languages[0]?.code ?? '';
}

// Parses one Server-Sent Event payload from the backend.
function parseAudioJobEvent(data: string): AudioJobStatusResponse | null {
  // Catches malformed event payloads so the UI can show a controlled error.
  try {
    // Parses the JSON status payload sent in the SSE data field.
    return JSON.parse(data) as AudioJobStatusResponse;
  // Handles invalid JSON from the event stream.
  } catch {
    // Signals that the event payload could not be parsed.
    return null;
  }
}

// Returns whether the job status means generation is still active.
function isActiveAudioJobStatus(status: AudioJobStatus | null): boolean {
  // Treats queued, summarizing, and generating as active states.
  return status === 'queued' || status === 'summarizing' || status === 'generating';
}

// Converts job state into user-visible status text.
function getGenerationStatus(
  // Receives the latest job status from the SSE stream.
  jobStatus: AudioJobStatus | null,
  // Receives the resolved audio URL used to detect completed output.
  resolvedAudioUrl: string | null,
): string {
  // Shows that the backend accepted the job and it is waiting to run.
  if (jobStatus === 'queued') {
    // Returns the queued status label.
    return 'Queued';
  }

  // Shows that the backend is summarizing before audio generation.
  if (jobStatus === 'summarizing') {
    // Returns the summarizing status label.
    return 'Summarizing text';
  }

  // Shows that the backend is producing the audio file.
  if (jobStatus === 'generating') {
    // Returns the generating status label.
    return 'Generating audio';
  }

  // Shows readiness when the generated audio URL is available.
  if (resolvedAudioUrl) {
    // Returns the completed status label.
    return 'Audio ready';
  }

  // Shows no status before generation starts or after a failure alert appears.
  return '';
}

// Defines the top-level React component for the text-to-speech UI.
export default function App() {
  // Stores the language options loaded from the backend.
  const [languages, setLanguages] = useState<LanguageOption[]>([]);
  // Stores the currently selected language code.
  const [languageCode, setLanguageCode] = useState('');
  // Stores the user's text input.
  const [text, setText] = useState('');
  // Stores whether the user wants the backend to summarize text first.
  const [summarize, setSummarize] = useState(false);
  // Stores the generated audio URL returned by the backend.
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  // Stores the optional summary returned by the backend.
  const [summarizedText, setSummarizedText] = useState<string | null>(null);
  // Tracks whether the language list request is still running.
  const [isLoadingLanguages, setIsLoadingLanguages] = useState(true);
  // Stores the latest async audio job status received from the SSE stream.
  const [jobStatus, setJobStatus] = useState<AudioJobStatus | null>(null);
  // Stores a user-visible error message when a request fails.
  const [error, setError] = useState<string | null>(null);
  // Stores the current EventSource connection so it can be closed later.
  const audioEventsRef = useRef<EventSource | null>(null);

  // Removes surrounding whitespace so blank input cannot be submitted.
  const trimmedText = text.trim();
  // Derives whether an audio job is currently running.
  const isGenerating = isActiveAudioJobStatus(jobStatus);
  // Enables generation only when there is text, a selected language, and no active request.
  const canGenerate = Boolean(trimmedText) && Boolean(languageCode) && !isGenerating;
  // Memoizes the browser-ready audio URL so it only recalculates when audioUrl changes.
  const resolvedAudioUrl = useMemo(
    // Converts the backend URL into a playable URL, or keeps null when no audio exists.
    () => (audioUrl ? buildAudioUrl(audioUrl) : null),
    // Re-runs the memoized calculation whenever the backend audio URL changes.
    [audioUrl],
  );
  // Builds the short status text announced below the form.
  const generationStatus = getGenerationStatus(jobStatus, resolvedAudioUrl);

  // Loads supported languages once when the component mounts.
  useEffect(() => {
    // Tracks whether the component is still mounted before setting state.
    let isMounted = true;

    // Defines the async language-loading workflow.
    async function loadLanguages() {
      // Attempts to fetch language options from the backend.
      try {
        // Requests the language list through the API client.
        const options = await fetchLanguages();
        // Stops if the component unmounted before the request completed.
        if (!isMounted) {
          // Exits without updating React state after unmount.
          return;
        }

        // Stores the loaded language options for the selector.
        setLanguages(options);
        // Chooses the initial selected language from the loaded options.
        setLanguageCode(getInitialLanguage(options));
      // Handles failures from the language-loading request.
      } catch (loadError) {
        // Stops if the component unmounted before the request failed.
        if (!isMounted) {
          // Exits without updating React state after unmount.
          return;
        }

        // Stores a displayable error message for the alert area.
        setError(
          // Uses the real Error message when the failure is an Error instance.
          loadError instanceof Error
            // Reads the message from the thrown Error.
            ? loadError.message
            // Falls back to a generic message for non-Error throws.
            : 'Could not load supported languages',
        );
      // Runs cleanup state changes after success or failure.
      } finally {
        // Updates loading state only while the component is still mounted.
        if (isMounted) {
          // Marks the language request as finished.
          setIsLoadingLanguages(false);
        }
      }
    }

    // Starts loading languages after the component has mounted.
    loadLanguages();

    // Returns a cleanup function for when the component unmounts.
    return () => {
      // Prevents late async responses from setting state after unmount.
      isMounted = false;
    };
  // Uses an empty dependency list so languages load only once.
  }, []);

  // Closes the SSE connection when the component unmounts.
  useEffect(() => {
    // Returns the cleanup function React runs during unmount.
    return () => {
      // Closes the current EventSource connection if one exists.
      audioEventsRef.current?.close();
      // Clears the stored EventSource reference.
      audioEventsRef.current = null;
    };
  // Uses an empty dependency list so cleanup is registered once.
  }, []);

  // Handles the form submission that asks the backend to generate audio.
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    // Prevents the browser from reloading the page on form submit.
    event.preventDefault();

    // Refuses to submit while required input is missing or generation is active.
    if (!canGenerate) {
      // Leaves state unchanged when generation is not allowed.
      return;
    }

    // Closes any previous SSE connection before starting a new job.
    audioEventsRef.current?.close();
    // Clears the previous EventSource reference.
    audioEventsRef.current = null;
    // Shows the queued state while the backend accepts and starts the job.
    setJobStatus('queued');
    // Clears any previous error before starting a fresh request.
    setError(null);
    // Clears old audio so stale playback is not shown during the new request.
    setAudioUrl(null);
    // Clears old summary text before receiving the next response.
    setSummarizedText(null);

    // Attempts to create an async audio job and subscribe to status events.
    try {
      // Creates the backend job with the trimmed text, selected language, and summarize option.
      const response = await createAudioJob({
        // Passes the whitespace-trimmed text to the backend.
        text: trimmedText,
        // Passes the currently selected language code to Kokoro via the API.
        language_code: languageCode,
        // Passes whether summarization should happen before speech generation.
        summarize,
      });

      // Opens an SSE connection for this job's progress stream.
      const eventSource = new EventSource(buildAudioJobEventsUrl(response.job_id));
      // Stores the EventSource so it can be closed on unmount or replacement.
      audioEventsRef.current = eventSource;

      // Handles each status event streamed by the backend.
      eventSource.onmessage = (message) => {
        // Parses the JSON payload from the SSE data field.
        const job = parseAudioJobEvent(message.data);
        // Handles malformed event payloads as a controlled failure.
        if (!job) {
          // Marks the job as failed so the form can be used again.
          setJobStatus('failed');
          // Shows a useful parse-failure message.
          setError('Could not read audio job update');
          // Closes the broken event stream.
          eventSource.close();
          // Clears the stored EventSource if it still points at this stream.
          if (audioEventsRef.current === eventSource) {
            // Removes the closed stream reference.
            audioEventsRef.current = null;
          }
          // Stops processing this malformed event.
          return;
        }

        // Stores the latest streamed job status.
        setJobStatus(job.status);

        // Handles successful terminal jobs.
        if (job.status === 'done') {
          // Checks that the done event contains an audio URL.
          if (job.audio_url) {
            // Stores the generated audio URL from the job event.
            setAudioUrl(job.audio_url);
            // Stores the optional summary text from the job event.
            setSummarizedText(job.summarized_text);
          // Handles an invalid done event without an audio URL.
          } else {
            // Stores a controlled error for the invalid terminal event.
            setError('Audio job finished without an audio URL');
            // Marks the job as failed so the form can be used again.
            setJobStatus('failed');
          }
          // Closes the completed event stream.
          eventSource.close();
          // Clears the stored EventSource if it still points at this stream.
          if (audioEventsRef.current === eventSource) {
            // Removes the closed stream reference.
            audioEventsRef.current = null;
          }
        }

        // Handles failed terminal jobs.
        if (job.status === 'failed') {
          // Shows the backend failure message or a generic fallback.
          setError(job.error ?? 'Could not generate audio');
          // Closes the failed event stream.
          eventSource.close();
          // Clears the stored EventSource if it still points at this stream.
          if (audioEventsRef.current === eventSource) {
            // Removes the closed stream reference.
            audioEventsRef.current = null;
          }
        }
      };

      // Handles network or connection-level SSE failures.
      eventSource.onerror = () => {
        // Marks the job as failed so the form can be used again.
        setJobStatus('failed');
        // Shows a clear stream-level error message.
        setError('Lost connection to audio job updates');
        // Closes the broken event stream.
        eventSource.close();
        // Clears the stored EventSource if it still points at this stream.
        if (audioEventsRef.current === eventSource) {
          // Removes the closed stream reference.
          audioEventsRef.current = null;
        }
      };
    // Handles request failures from the API client.
    } catch (generateError) {
      // Clears the queued state because job creation failed before SSE started.
      setJobStatus(null);
      // Stores a displayable error message for the alert area.
      setError(
        // Uses the real Error message when one was thrown.
        generateError instanceof Error
          // Reads the message from the thrown Error.
          ? generateError.message
          // Falls back to a generic message for non-Error throws.
          : 'Could not generate audio',
      );
    }
  }

  // Renders the application UI.
  return (
    // Provides the main page landmark and outer layout wrapper.
    <main className="app-shell">
      {/* Frames the interactive generator and links it to the heading for accessibility. */}
      <section className="tool-panel" aria-labelledby="app-title">
        {/* Groups the eyebrow label and main heading. */}
        <div className="title-block">
          {/* Displays the small category label above the title. */}
          <p className="eyebrow">Text to speech</p>
          {/* Displays the main application title. */}
          <h1 id="app-title">AI Podcaster</h1>
        </div>

        {/* Wraps the language, text, summarize, and submit controls. */}
        <form className="generator-form" onSubmit={handleSubmit}>
          {/* Labels the language selector so screen readers can identify it. */}
          <label className="field">
            {/* Displays the visible language selector label. */}
            <span>Select a language</span>
            {/* Lets the user choose the speech language. */}
            <select
              /* Keeps the select value synchronized with React state. */
              value={languageCode}
              /* Updates the selected language when the user changes the dropdown. */
              onChange={(event) => setLanguageCode(event.target.value)}
              /* Prevents language changes while loading options or generating audio. */
              disabled={isLoadingLanguages || isGenerating}
            >
              {/* Renders one option for each backend-supported language. */}
              {languages.map((language) => (
                /* Uses the stable language code as the React key and submitted value. */
                <option key={language.code} value={language.code}>
                  {/* Shows the language's user-facing label. */}
                  {language.label}
                </option>
              ))}
            </select>
          </label>

          {/* Labels the text input area so screen readers can identify it. */}
          <label className="field">
            {/* Displays the visible text input label. */}
            <span>Enter text</span>
            {/* Lets the user enter the content to summarize or convert to speech. */}
            <textarea
              /* Keeps the textarea value synchronized with React state. */
              value={text}
              /* Updates the stored text whenever the user types. */
              onChange={(event) => setText(event.target.value)}
              /* Gives the textarea a comfortable default height. */
              rows={10}
              /* Prevents editing while the backend is generating audio. */
              disabled={isGenerating}
            />
          </label>

          {/* Labels the summarization checkbox as one clickable row. */}
          <label className="checkbox-row">
            {/* Lets the user opt into backend summarization before audio generation. */}
            <input
              /* Declares this control as a checkbox. */
              type="checkbox"
              /* Keeps the checked state synchronized with React state. */
              checked={summarize}
              /* Updates the summarize option when the user toggles the checkbox. */
              onChange={(event) => setSummarize(event.target.checked)}
              /* Prevents changing the option during an active generation request. */
              disabled={isGenerating}
            />
            {/* Displays the visible checkbox label. */}
            <span>Summarize text</span>
          </label>

          {/* Submits the form when generation is allowed. */}
          <button type="submit" disabled={!canGenerate}>
            {/* Shows progress text while loading and action text otherwise. */}
            {isGenerating ? 'Generating audio' : 'Generate Audio'}
          </button>
        </form>

        {/* Renders status text only after generation starts or completes. */}
        {generationStatus ? (
          // Announces generation progress and completion to assistive technology.
          <p className="generation-status" role="status">
            {/* Displays the current generation status string. */}
            {generationStatus}
          </p>
        // Renders nothing when there is no status to show.
        ) : null}

        {/* Renders the error alert only when an error message exists. */}
        {error ? (
          // Uses role="alert" so assistive technology announces request failures.
          <p className="error-message" role="alert">
            {/* Displays the current request error message. */}
            {error}
          </p>
        // Renders nothing when there is no error.
        ) : null}

        {/* Renders the result area only after the backend returns an audio URL. */}
        {resolvedAudioUrl ? (
          // Groups the generated audio player and optional summary.
          <section className="result-panel" aria-label="Generated result">
            {/* Provides playback controls for the generated audio file. */}
            <audio aria-label="Generated audio" controls src={resolvedAudioUrl} />

            {/* Renders generated summary text only when the backend returned it. */}
            {summarizedText ? (
              // Frames the optional generated summary.
              <div className="summary-panel">
                {/* Labels the generated summary section. */}
                <h2>Generated text</h2>
                {/* Displays the generated summary text. */}
                <p>{summarizedText}</p>
              </div>
            // Renders nothing when summarization was not requested.
            ) : null}
          </section>
        // Renders nothing before audio has been generated.
        ) : null}
      </section>
    </main>
  );
}
