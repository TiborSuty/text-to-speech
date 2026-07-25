import { afterEach, describe, expect, it, vi } from 'vitest';

import { buildAudioUrl, fetchLanguages, generateAudio } from './api';
import type { AudioRequest } from './types';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('api client', () => {
  it('fetches language options', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [{ label: 'American English', code: 'a' }],
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchLanguages();

    expect(fetchMock).toHaveBeenCalledWith('/api/languages', {
      headers: { Accept: 'application/json' },
    });
    expect(result).toEqual([{ label: 'American English', code: 'a' }]);
  });

  it('posts audio generation requests', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ audio_url: '/audios/audio.wav', summarized_text: null }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const payload: AudioRequest = {
      text: 'Hello',
      language_code: 'a',
      summarize: false,
    };

    const result = await generateAudio(payload);

    expect(fetchMock).toHaveBeenCalledWith('/api/audio', {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });
    expect(result).toEqual({
      audio_url: '/audios/audio.wav',
      summarized_text: null,
    });
  });

  it('turns backend errors into thrown messages', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({ detail: 'Could not generate audio' }),
      }),
    );

    await expect(
      generateAudio({ text: 'Hello', language_code: 'a', summarize: false }),
    ).rejects.toThrow('Could not generate audio');
  });

  it('keeps relative audio URLs relative when no API base URL is configured', () => {
    expect(buildAudioUrl('/audios/audio.wav')).toBe('/audios/audio.wav');
  });
});
