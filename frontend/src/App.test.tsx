// Imports React Testing Library helpers for rendering, querying, and flushing UI updates.
import { act, render, screen, waitFor } from '@testing-library/react';
// Imports user-event to simulate realistic browser interactions.
import userEvent from '@testing-library/user-event';
// Imports Vitest helpers for setup, cleanup, grouping, assertions, and mocks.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// Imports the component under test.
import App from './App';
// Imports API helpers that will be mocked in these component tests.
import { buildAudioJobEventsUrl, buildAudioUrl, createAudioJob, fetchLanguages } from './api';
// Imports the type used by the mocked SSE payloads.
import type { AudioJobStatusResponse } from './types';

// Replaces the real API module with controllable test doubles.
vi.mock('./api', () => ({
  // Mocks the SSE URL builder with a predictable local URL.
  buildAudioJobEventsUrl: vi.fn((jobId: string) => `/api/audio-jobs/${jobId}/events`),
  // Mocks audio URL resolution with a predictable local backend URL.
  buildAudioUrl: vi.fn((audioUrl: string) => `http://127.0.0.1:8000${audioUrl}`),
  // Mocks the async audio job creation API function.
  createAudioJob: vi.fn(),
  // Mocks the language-loading API function.
  fetchLanguages: vi.fn(),
}));

// Defines the minimal EventSource shape needed by the component tests.
class MockEventSource {
  // Stores every constructed mock EventSource instance.
  static instances: MockEventSource[] = [];
  // Stores the URL this mock connection was opened with.
  url: string;
  // Stores whether close was called.
  closed = false;
  // Stores the message handler assigned by the component.
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  // Stores the error handler assigned by the component.
  onerror: ((event: Event) => void) | null = null;

  // Creates a mock EventSource connection.
  constructor(url: string) {
    // Stores the URL for later assertions.
    this.url = url;
    // Records this instance so tests can emit events through it.
    MockEventSource.instances.push(this);
  }

  // Emits one backend job status payload through the message handler.
  emit(payload: AudioJobStatusResponse) {
    // Calls the registered message handler when one exists.
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent<string>);
  }

  // Emits one stream error through the error handler.
  fail() {
    // Calls the registered error handler when one exists.
    this.onerror?.(new Event('error'));
  }

  // Closes this mock EventSource connection.
  close() {
    // Marks the mock connection as closed.
    this.closed = true;
  }
}

// Provides shared language options for tests.
const languages = [
  // Adds the default American English option.
  { label: 'American English', code: 'a' },
  // Adds a second option so the dropdown has more than one choice.
  { label: 'British English', code: 'b' },
];

// Resets mocked API behavior before each test.
beforeEach(() => {
  // Clears EventSource instances recorded by previous tests.
  MockEventSource.instances = [];
  // Installs the mock EventSource constructor globally.
  vi.stubGlobal('EventSource', MockEventSource);
  // Reinstalls the default SSE URL builder implementation.
  vi.mocked(buildAudioJobEventsUrl).mockImplementation(
    // Builds the same backend-relative URL the real helper returns.
    (jobId: string) => `/api/audio-jobs/${jobId}/events`,
  );
  // Reinstalls the default audio URL resolver implementation.
  vi.mocked(buildAudioUrl).mockImplementation(
    // Prefixes backend-relative audio URLs with the local test backend URL.
    (audioUrl: string) => `http://127.0.0.1:8000${audioUrl}`,
  );
  // Makes the language API return the shared language list by default.
  vi.mocked(fetchLanguages).mockResolvedValue(languages);
  // Makes async audio job creation succeed with a default job ID by default.
  vi.mocked(createAudioJob).mockResolvedValue({ job_id: 'job-123' });
});

// Runs cleanup after each test.
afterEach(() => {
  // Removes mocked globals such as EventSource.
  vi.unstubAllGlobals();
});

// Groups component tests for the App UI.
describe('App', () => {
  // Verifies initial language loading and default selection.
  it('loads languages and defaults to American English', async () => {
    // Renders the application component.
    render(<App />);

    // Waits for the language selector to appear after async loading.
    const select = await screen.findByLabelText(/select a language/i);

    // Confirms American English is selected by default.
    expect(select).toHaveValue('a');
    // Confirms the dropdown includes the second mocked language.
    expect(screen.getByRole('option', { name: 'British English' })).toBeInTheDocument();
  });

  // Verifies users cannot submit an empty text value.
  it('keeps the generate button disabled for blank text', async () => {
    // Renders the application component.
    render(<App />);

    // Waits for the submit button to appear after initial rendering.
    const button = await screen.findByRole('button', { name: /generate audio/i });

    // Confirms the button is disabled while no text has been entered.
    expect(button).toBeDisabled();
  });

  // Verifies a successful SSE generation flow displays the audio player.
  it('submits text and displays the generated audio player', async () => {
    // Creates a user-event instance for typing and clicking.
    const user = userEvent.setup();
    // Renders the application component.
    render(<App />);

    // Types input text into the textarea after it becomes available.
    await user.type(await screen.findByLabelText(/enter text/i), 'Hello world');
    // Clicks the enabled generate button.
    await user.click(screen.getByRole('button', { name: /generate audio/i }));

    // Waits until the async createAudioJob mock has been called.
    await waitFor(() => {
      // Confirms the component submitted the expected request payload.
      expect(createAudioJob).toHaveBeenCalledWith({
        // Confirms the typed text is submitted.
        text: 'Hello world',
        // Confirms the default language code is submitted.
        language_code: 'a',
        // Confirms summarization remains disabled by default.
        summarize: false,
      });
    });

    // Waits until the component opens the SSE connection.
    await waitFor(() => {
      // Confirms one EventSource connection was created.
      expect(MockEventSource.instances).toHaveLength(1);
    });

    // Emits the terminal done event through the mocked SSE stream.
    act(() => {
      // Sends the same payload shape the backend streams on completion.
      MockEventSource.instances[0].emit({
        // Identifies the completed job.
        job_id: 'job-123',
        // Marks the job as completed.
        status: 'done',
        // Supplies the generated backend-relative audio path.
        audio_url: '/audios/audio.wav',
        // Leaves summary text empty for this test.
        summarized_text: null,
        // Leaves error empty for successful completion.
        error: null,
      });
    });

    // Waits for the generated audio player and verifies its source URL.
    expect(await screen.findByLabelText(/generated audio/i)).toHaveAttribute(
      // Checks the audio element's src attribute.
      'src',
      // Confirms the mocked URL builder was used.
      'http://127.0.0.1:8000/audios/audio.wav',
    );
  });

  // Verifies that the UI announces completed audio generation.
  it('announces when generated audio is ready', async () => {
    // Creates a user-event instance for typing and clicking.
    const user = userEvent.setup();
    // Renders the application component.
    render(<App />);

    // Types input text into the textarea after it becomes available.
    await user.type(await screen.findByLabelText(/enter text/i), 'Hello world');
    // Clicks the enabled generate button.
    await user.click(screen.getByRole('button', { name: /generate audio/i }));

    // Waits until the component opens the SSE connection.
    await waitFor(() => {
      // Confirms one EventSource connection was created.
      expect(MockEventSource.instances).toHaveLength(1);
    });

    // Emits the terminal done event through the mocked SSE stream.
    act(() => {
      // Sends the same payload shape the backend streams on completion.
      MockEventSource.instances[0].emit({
        // Identifies the completed job.
        job_id: 'job-123',
        // Marks the job as completed.
        status: 'done',
        // Supplies the generated backend-relative audio path.
        audio_url: '/audios/audio.wav',
        // Leaves summary text empty for this test.
        summarized_text: null,
        // Leaves error empty for successful completion.
        error: null,
      });
    });

    // Confirms the status region reports the completed state.
    expect(await screen.findByRole('status')).toHaveTextContent('Audio ready');
  });

  // Verifies that returned summary text is displayed.
  it('shows summarized text returned by the backend', async () => {
    // Creates a user-event instance for typing and clicking.
    const user = userEvent.setup();

    // Renders the application component.
    render(<App />);

    // Types input text into the textarea after it becomes available.
    await user.type(await screen.findByLabelText(/enter text/i), 'Long text');
    // Enables the summarize option before submitting.
    await user.click(screen.getByLabelText(/summarize text/i));
    // Clicks the generate button to submit the form.
    await user.click(screen.getByRole('button', { name: /generate audio/i }));

    // Waits until the component opens the SSE connection.
    await waitFor(() => {
      // Confirms one EventSource connection was created.
      expect(MockEventSource.instances).toHaveLength(1);
    });

    // Emits the terminal done event with summary text.
    act(() => {
      // Sends the same payload shape the backend streams on completion.
      MockEventSource.instances[0].emit({
        // Identifies the completed job.
        job_id: 'job-123',
        // Marks the job as completed.
        status: 'done',
        // Supplies the generated backend-relative audio path.
        audio_url: '/audios/audio.wav',
        // Supplies summary text that should appear in the UI.
        summarized_text: 'Short summary.',
        // Leaves error empty for successful completion.
        error: null,
      });
    });

    // Confirms the returned summary text is rendered.
    expect(await screen.findByText('Short summary.')).toBeInTheDocument();
  });

  // Verifies job creation API failures appear as visible alerts.
  it('shows job creation API errors', async () => {
    // Creates a user-event instance for typing and clicking.
    const user = userEvent.setup();
    // Makes async job creation reject with a displayable error.
    vi.mocked(createAudioJob).mockRejectedValue(new Error('Could not create audio job'));

    // Renders the application component.
    render(<App />);

    // Types input text into the textarea after it becomes available.
    await user.type(await screen.findByLabelText(/enter text/i), 'Hello');
    // Clicks the generate button to trigger the rejected request.
    await user.click(screen.getByRole('button', { name: /generate audio/i }));

    // Confirms the error alert displays the rejected Error message.
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not create audio job');
  });

  // Verifies streamed job failures appear as visible alerts.
  it('shows streamed job errors', async () => {
    // Creates a user-event instance for typing and clicking.
    const user = userEvent.setup();
    // Renders the application component.
    render(<App />);

    // Types input text into the textarea after it becomes available.
    await user.type(await screen.findByLabelText(/enter text/i), 'Hello');
    // Clicks the generate button to create the async job.
    await user.click(screen.getByRole('button', { name: /generate audio/i }));

    // Waits until the component opens the SSE connection.
    await waitFor(() => {
      // Confirms one EventSource connection was created.
      expect(MockEventSource.instances).toHaveLength(1);
    });

    // Emits a terminal failed event through the mocked SSE stream.
    act(() => {
      // Sends the same payload shape the backend streams on failure.
      MockEventSource.instances[0].emit({
        // Identifies the failed job.
        job_id: 'job-123',
        // Marks the job as failed.
        status: 'failed',
        // Leaves audio URL empty because the job failed.
        audio_url: null,
        // Leaves summary text empty because the job failed.
        summarized_text: null,
        // Supplies the backend error message that should appear in the UI.
        error: 'Could not generate audio',
      });
    });

    // Confirms the error alert displays the streamed failure message.
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not generate audio');
  });
});
