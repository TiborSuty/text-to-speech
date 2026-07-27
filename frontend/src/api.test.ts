// Imports Vitest helpers for structuring tests, assertions, and mocks.
import { afterEach, describe, expect, it, vi } from 'vitest';

// Imports the API helpers under test.
import {
  buildAudioJobEventsUrl,
  buildAudioUrl,
  createAudioJob,
  fetchLanguages,
  generateAudio,
} from './api';
// Imports the request type used to build a typed test payload.
import type { AudioRequest } from './types';

// Runs cleanup after each test in this file.
afterEach(() => {
  // Removes mocked globals such as fetch so tests do not leak state.
  vi.unstubAllGlobals();
});

// Groups tests for the frontend API client helpers.
describe('api client', () => {
  // Verifies the language-fetching helper calls the right endpoint.
  it('fetches language options', async () => {
    // Creates a mocked fetch response containing one language option.
    const fetchMock = vi.fn().mockResolvedValue({
      // Marks the mocked response as successful.
      ok: true,
      // Returns language JSON when the client reads the response body.
      json: async () => [{ label: 'American English', code: 'a' }],
    });
    // Installs the mocked fetch function as the global fetch implementation.
    vi.stubGlobal('fetch', fetchMock);

    // Calls the production helper being tested.
    const result = await fetchLanguages();

    // Confirms the helper requested the expected language endpoint and headers.
    expect(fetchMock).toHaveBeenCalledWith('/api/languages', {
      // Confirms the helper asks for a JSON response.
      headers: { Accept: 'application/json' },
    });
    // Confirms the helper returns the parsed language array.
    expect(result).toEqual([{ label: 'American English', code: 'a' }]);
  });

  // Verifies the audio-generation helper posts the correct request.
  it('posts audio generation requests', async () => {
    // Creates a mocked successful fetch response for generated audio.
    const fetchMock = vi.fn().mockResolvedValue({
      // Marks the mocked response as successful.
      ok: true,
      // Returns the JSON body expected from the backend.
      json: async () => ({ audio_url: '/audios/audio.wav', summarized_text: null }),
    });
    // Installs the mocked fetch function as the global fetch implementation.
    vi.stubGlobal('fetch', fetchMock);

    // Builds the typed request payload that should be sent to the backend.
    const payload: AudioRequest = {
      // Supplies the text to generate audio from.
      text: 'Hello',
      // Supplies the selected Kokoro language code.
      language_code: 'a',
      // Disables summarization for this request.
      summarize: false,
    };

    // Calls the production helper being tested.
    const result = await generateAudio(payload);

    // Confirms the helper requested the expected audio endpoint and request options.
    expect(fetchMock).toHaveBeenCalledWith('/api/audio', {
      // Confirms the helper uses POST for generation.
      method: 'POST',
      // Confirms the helper sends and accepts JSON.
      headers: {
        // Confirms the helper asks for a JSON response.
        Accept: 'application/json',
        // Confirms the helper declares a JSON request body.
        'Content-Type': 'application/json',
      },
      // Confirms the helper serializes the payload as JSON.
      body: JSON.stringify(payload),
    });
    // Confirms the helper returns the parsed audio response.
    expect(result).toEqual({
      // Confirms the generated audio URL is preserved.
      audio_url: '/audios/audio.wav',
      // Confirms a missing summary remains null.
      summarized_text: null,
    });
  });

  // Verifies backend error details become thrown Error messages.
  it('turns backend errors into thrown messages', async () => {
    // Installs a mocked fetch function that returns a failed response.
    vi.stubGlobal(
      // Names the global function being mocked.
      'fetch',
      // Creates the mocked failed fetch response.
      vi.fn().mockResolvedValue({
        // Marks the mocked response as failed.
        ok: false,
        // Supplies the HTTP status used by the fallback message.
        status: 500,
        // Supplies the backend error detail the client should prefer.
        json: async () => ({ detail: 'Could not generate audio' }),
      }),
    );

    // Calls the helper and asserts that it rejects with the backend message.
    await expect(
      // Sends a valid request body so only the mocked response controls the failure.
      generateAudio({ text: 'Hello', language_code: 'a', summarize: false }),
    // Confirms the thrown Error message is the backend detail.
    ).rejects.toThrow('Could not generate audio');
  });

  // Verifies the async audio-job helper posts the correct request.
  it('posts async audio job requests', async () => {
    // Creates a mocked successful fetch response for a created job.
    const fetchMock = vi.fn().mockResolvedValue({
      // Marks the mocked response as successful.
      ok: true,
      // Returns the JSON body expected from the async job endpoint.
      json: async () => ({ job_id: 'job-123' }),
    });
    // Installs the mocked fetch function as the global fetch implementation.
    vi.stubGlobal('fetch', fetchMock);

    // Builds the typed request payload that should be sent to the backend.
    const payload: AudioRequest = {
      // Supplies the text to generate audio from.
      text: 'Hello',
      // Supplies the selected Kokoro language code.
      language_code: 'a',
      // Disables summarization for this request.
      summarize: false,
    };

    // Calls the production helper being tested.
    const result = await createAudioJob(payload);

    // Confirms the helper requested the expected async job endpoint and request options.
    expect(fetchMock).toHaveBeenCalledWith('/api/audio-jobs', {
      // Confirms the helper uses POST for job creation.
      method: 'POST',
      // Confirms the helper sends and accepts JSON.
      headers: {
        // Confirms the helper asks for a JSON response.
        Accept: 'application/json',
        // Confirms the helper declares a JSON request body.
        'Content-Type': 'application/json',
      },
      // Confirms the helper serializes the payload as JSON.
      body: JSON.stringify(payload),
    });
    // Confirms the helper returns the parsed job creation response.
    expect(result).toEqual({ job_id: 'job-123' });
  });

  // Verifies the async audio-job SSE URL builder.
  it('builds audio job event stream URLs', () => {
    // Confirms the helper builds the backend-relative EventSource URL.
    expect(buildAudioJobEventsUrl('job 123')).toBe('/api/audio-jobs/job%20123/events');
  });

  // Verifies relative audio URLs stay relative without a configured API base URL.
  it('keeps relative audio URLs relative when no API base URL is configured', () => {
    // Confirms the helper returns the unchanged relative audio path.
    expect(buildAudioUrl('/audios/audio.wav')).toBe('/audios/audio.wav');
  });
});
