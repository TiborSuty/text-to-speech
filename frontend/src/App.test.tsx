import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import App from './App';
import { buildAudioUrl, fetchLanguages, generateAudio } from './api';

vi.mock('./api', () => ({
  buildAudioUrl: vi.fn((audioUrl: string) => `http://127.0.0.1:8000${audioUrl}`),
  fetchLanguages: vi.fn(),
  generateAudio: vi.fn(),
}));

const languages = [
  { label: 'American English', code: 'a' },
  { label: 'British English', code: 'b' },
];

beforeEach(() => {
  vi.mocked(buildAudioUrl).mockImplementation(
    (audioUrl: string) => `http://127.0.0.1:8000${audioUrl}`,
  );
  vi.mocked(fetchLanguages).mockResolvedValue(languages);
  vi.mocked(generateAudio).mockResolvedValue({
    audio_url: '/audios/audio.wav',
    summarized_text: null,
  });
});

describe('App', () => {
  it('loads languages and defaults to American English', async () => {
    render(<App />);

    const select = await screen.findByLabelText(/select a language/i);

    expect(select).toHaveValue('a');
    expect(screen.getByRole('option', { name: 'British English' })).toBeInTheDocument();
  });

  it('keeps the generate button disabled for blank text', async () => {
    render(<App />);

    const button = await screen.findByRole('button', { name: /generate audio/i });

    expect(button).toBeDisabled();
  });

  it('submits text and displays the generated audio player', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.type(await screen.findByLabelText(/enter text/i), 'Hello world');
    await user.click(screen.getByRole('button', { name: /generate audio/i }));

    await waitFor(() => {
      expect(generateAudio).toHaveBeenCalledWith({
        text: 'Hello world',
        language_code: 'a',
        summarize: false,
      });
    });

    expect(await screen.findByLabelText(/generated audio/i)).toHaveAttribute(
      'src',
      'http://127.0.0.1:8000/audios/audio.wav',
    );
  });

  it('announces when generated audio is ready', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.type(await screen.findByLabelText(/enter text/i), 'Hello world');
    await user.click(screen.getByRole('button', { name: /generate audio/i }));

    expect(await screen.findByRole('status')).toHaveTextContent('Audio ready');
  });

  it('shows summarized text returned by the backend', async () => {
    const user = userEvent.setup();
    vi.mocked(generateAudio).mockResolvedValue({
      audio_url: '/audios/audio.wav',
      summarized_text: 'Short summary.',
    });

    render(<App />);

    await user.type(await screen.findByLabelText(/enter text/i), 'Long text');
    await user.click(screen.getByLabelText(/summarize text/i));
    await user.click(screen.getByRole('button', { name: /generate audio/i }));

    expect(await screen.findByText('Short summary.')).toBeInTheDocument();
  });

  it('shows API errors', async () => {
    const user = userEvent.setup();
    vi.mocked(generateAudio).mockRejectedValue(new Error('Could not generate audio'));

    render(<App />);

    await user.type(await screen.findByLabelText(/enter text/i), 'Hello');
    await user.click(screen.getByRole('button', { name: /generate audio/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not generate audio');
  });
});
