import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { buildAudioJobDownloadUrl, buildAudioJobEventsUrl, buildAudioUrl, approvePodcastWorkflow, cancelAudioJob, createAudioJob, deleteAudioJob, fetchAppConfig, fetchAudioJobs, fetchLanguages, fetchPodcastWorkflow, startPodcastWorkflow, } from './api';
import type { AudioJobStatusResponse } from './types';
vi.mock('./api', () => ({
    buildAudioJobEventsUrl: vi.fn((jobId: string) => `/api/audio-jobs/${jobId}/events`),
    buildAudioJobDownloadUrl: vi.fn((jobId: string) => `/api/audio-jobs/${jobId}/download`),
    buildAudioUrl: vi.fn((audioUrl: string) => `http://127.0.0.1:8000${audioUrl}`),
    createAudioJob: vi.fn(),
    cancelAudioJob: vi.fn(),
    fetchAudioJobs: vi.fn(),
    fetchAppConfig: vi.fn(),
    startPodcastWorkflow: vi.fn(),
    fetchPodcastWorkflow: vi.fn(),
    approvePodcastWorkflow: vi.fn(),
    deleteAudioJob: vi.fn(),
    fetchLanguages: vi.fn(),
}));
class MockEventSource {
    static instances: MockEventSource[] = [];
    url: string;
    closed = false;
    onmessage: ((event: MessageEvent<string>) => void) | null = null;
    onopen: ((event: Event) => void) | null = null;
    onerror: ((event: Event) => void) | null = null;
    constructor(url: string) {
        this.url = url;
        MockEventSource.instances.push(this);
    }
    emit(payload: AudioJobStatusResponse) {
        this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent<string>);
    }
    fail() {
        this.onerror?.(new Event('error'));
    }
    reopen() {
        this.onopen?.(new Event('open'));
    }
    close() {
        this.closed = true;
    }
}
const languages = [
    {
        label: 'American English',
        code: 'a',
        default_voice: 'af_heart',
        voices: [
            { id: 'af_heart', label: 'Heart (Female)' },
            { id: 'af_bella', label: 'Bella (Female)' },
        ],
    },
    {
        label: 'British English',
        code: 'b',
        default_voice: 'bf_emma',
        voices: [
            { id: 'bf_emma', label: 'Emma (Female)' },
            { id: 'bm_george', label: 'George (Male)' },
        ],
    },
];
function createAudioJobStatus(overrides: Partial<AudioJobStatusResponse> = {}): AudioJobStatusResponse {
    return {
        job_id: 'job-123',
        status: 'done',
        queue_position: null,
        progress: 100,
        language_code: 'a',
        voice: 'af_heart',
        summarize: false,
        text_preview: 'Hello world',
        created_at: '2026-07-28T12:00:00Z',
        updated_at: '2026-07-28T12:01:00Z',
        audio_url: '/audios/job-123.wav',
        summarized_text: null,
        error: null,
        ...overrides,
    };
}
beforeEach(() => {
    vi.clearAllMocks();
    const storedValues = new Map<string, string>();
    vi.stubGlobal('localStorage', {
        getItem: (key: string) => storedValues.get(key) ?? null,
        setItem: (key: string, value: string) => storedValues.set(key, value),
        removeItem: (key: string) => storedValues.delete(key),
        clear: () => storedValues.clear(),
    });
    MockEventSource.instances = [];
    vi.stubGlobal('EventSource', MockEventSource);
    vi.mocked(buildAudioJobEventsUrl).mockImplementation((jobId: string) => `/api/audio-jobs/${jobId}/events`);
    vi.mocked(buildAudioJobDownloadUrl).mockImplementation((jobId: string) => `/api/audio-jobs/${jobId}/download`);
    vi.mocked(buildAudioUrl).mockImplementation((audioUrl: string) => `http://127.0.0.1:8000${audioUrl}`);
    vi.mocked(fetchLanguages).mockResolvedValue(languages);
    vi.mocked(fetchAudioJobs).mockResolvedValue([]);
    vi.mocked(fetchAppConfig).mockResolvedValue({ max_text_characters: 50000 });
    vi.mocked(deleteAudioJob).mockResolvedValue();
    vi.mocked(startPodcastWorkflow).mockResolvedValue({
        workflow_id: 'workflow-123',
        status: 'awaiting_review',
        script: {
            title: 'Inside SQLite',
            segments: [
                { speaker: 'host', text: 'Where does SQLite run?' },
                { speaker: 'guest', text: 'Inside the application process.' },
            ],
        },
        facts: ['SQLite runs inside an application.'],
        issues: [],
        revision_count: 1,
        audio_job_id: null,
    });
    vi.mocked(fetchPodcastWorkflow).mockResolvedValue({
        workflow_id: 'workflow-123',
        status: 'awaiting_review',
        script: {
            title: 'Inside SQLite',
            segments: [
                { speaker: 'host', text: 'Where does SQLite run?' },
                { speaker: 'guest', text: 'Inside the application process.' },
            ],
        },
        facts: ['SQLite runs inside an application.'],
        issues: [],
        revision_count: 1,
        audio_job_id: null,
    });
    vi.mocked(approvePodcastWorkflow).mockResolvedValue({ job_id: 'job-123' });
    vi.mocked(cancelAudioJob).mockResolvedValue(createAudioJobStatus({
        status: 'cancelled',
        audio_url: null,
    }));
    vi.mocked(createAudioJob).mockResolvedValue({ job_id: 'job-123' });
});
afterEach(() => {
    vi.unstubAllGlobals();
});
describe('App', () => {
    it('loads languages and defaults to American English', async () => {
        render(<App />);
        const select = await screen.findByLabelText(/select a language/i);
        expect(select).toHaveValue('a');
        expect(screen.getByRole('option', { name: 'British English' })).toBeInTheDocument();
        expect(screen.getByLabelText(/select a voice/i)).toHaveValue('af_heart');
    });
    it('updates available voices when the language changes', async () => {
        const user = userEvent.setup();
        render(<App />);
        await user.selectOptions(await screen.findByLabelText(/select a language/i), 'b');
        expect(screen.getByLabelText(/select a voice/i)).toHaveValue('bf_emma');
        expect(screen.queryByRole('option', { name: 'Heart (Female)' })).not.toBeInTheDocument();
        expect(screen.getByRole('option', { name: 'George (Male)' })).toBeInTheDocument();
    });
    it('keeps the generate button disabled for blank text', async () => {
        render(<App />);
        const button = await screen.findByRole('button', { name: /generate audio/i });
        expect(button).toBeDisabled();
    });
    it('submits text and displays the generated audio player', async () => {
        const user = userEvent.setup();
        render(<App />);
        await user.selectOptions(await screen.findByLabelText(/select a voice/i), 'af_bella');
        await user.type(await screen.findByLabelText(/enter text/i), 'Hello world');
        await user.click(screen.getByRole('button', { name: /generate audio/i }));
        await waitFor(() => {
            expect(createAudioJob).toHaveBeenCalledWith({
                text: 'Hello world',
                language_code: 'a',
                voice: 'af_bella',
                summarize: false,
            });
        });
        await waitFor(() => {
            expect(MockEventSource.instances).toHaveLength(1);
        });
        act(() => {
            MockEventSource.instances[0].emit(createAudioJobStatus({
                job_id: 'job-123',
                status: 'done',
                audio_url: '/audios/job-123.wav',
                summarized_text: null,
                error: null,
            }));
        });
        expect(await screen.findByLabelText('Generated audio', { exact: true })).toHaveAttribute('src', 'http://127.0.0.1:8000/audios/job-123.wav');
    });
    it('announces when generated audio is ready', async () => {
        const user = userEvent.setup();
        render(<App />);
        await user.type(await screen.findByLabelText(/enter text/i), 'Hello world');
        await user.click(screen.getByRole('button', { name: /generate audio/i }));
        await waitFor(() => {
            expect(MockEventSource.instances).toHaveLength(1);
        });
        act(() => {
            MockEventSource.instances[0].emit(createAudioJobStatus({
                job_id: 'job-123',
                status: 'done',
                audio_url: '/audios/job-123.wav',
                summarized_text: null,
                error: null,
            }));
        });
        expect(await screen.findByRole('status')).toHaveTextContent('Audio ready');
    });
    it('shows the streamed queue position', async () => {
        const user = userEvent.setup();
        render(<App />);
        await user.type(await screen.findByLabelText(/enter text/i), 'Queued text');
        await user.click(screen.getByRole('button', { name: /generate audio/i }));
        await waitFor(() => {
            expect(MockEventSource.instances).toHaveLength(1);
        });
        act(() => {
            MockEventSource.instances[0].emit(createAudioJobStatus({
                status: 'queued',
                queue_position: 2,
                audio_url: null,
            }));
        });
        expect(await screen.findByRole('status')).toHaveTextContent('Queued · Position 2');
    });
    it('shows streamed generation progress', async () => {
        const user = userEvent.setup();
        render(<App />);
        await user.type(await screen.findByLabelText(/enter text/i), 'Progress text');
        await user.click(screen.getByRole('button', { name: /generate audio/i }));
        await waitFor(() => {
            expect(MockEventSource.instances).toHaveLength(1);
        });
        act(() => {
            MockEventSource.instances[0].emit(createAudioJobStatus({
                status: 'generating',
                progress: 42,
                audio_url: null,
            }));
        });
        expect(await screen.findByRole('status')).toHaveTextContent('Generating audio · 42%');
        expect(screen.getByLabelText('Audio generation progress')).toHaveAttribute('value', '42');
    });
    it('recovers after an SSE disconnect and receives the terminal result', async () => {
        const user = userEvent.setup();
        render(<App />);
        await user.type(await screen.findByLabelText(/enter text/i), 'Reconnect text');
        await user.click(screen.getByRole('button', { name: /generate audio/i }));
        await waitFor(() => {
            expect(MockEventSource.instances).toHaveLength(1);
        });
        const eventSource = MockEventSource.instances[0];
        act(() => {
            eventSource.emit(createAudioJobStatus({
                status: 'generating',
                progress: 42,
                audio_url: null,
            }));
        });
        act(() => {
            eventSource.fail();
        });
        expect(await screen.findByRole('status')).toHaveTextContent('Connection lost · Reconnecting');
        expect(eventSource.closed).toBe(false);
        expect(screen.getAllByRole('button', { name: 'Cancel' })).toHaveLength(2);
        expect(screen.getAllByRole('button', { name: 'Cancel' }).every((button) => !button.hasAttribute('disabled'))).toBe(true);
        expect(screen.queryByRole('alert')).not.toBeInTheDocument();
        act(() => {
            eventSource.reopen();
        });
        expect(await screen.findByRole('status')).toHaveTextContent('Generating audio · 42%');
        act(() => {
            eventSource.emit(createAudioJobStatus({
                status: 'done',
                progress: 100,
                audio_url: '/audios/job-123.wav',
            }));
        });
        expect(await screen.findByLabelText('Generated audio', { exact: true })).toHaveAttribute('src', 'http://127.0.0.1:8000/audios/job-123.wav');
        expect(screen.getByRole('status')).toHaveTextContent('Audio ready');
        expect(eventSource.closed).toBe(true);
    });
    it('cancels the current audio job', async () => {
        const user = userEvent.setup();
        render(<App />);
        await user.type(await screen.findByLabelText(/enter text/i), 'Cancel this');
        await user.click(screen.getByRole('button', { name: /generate audio/i }));
        const cancelButton = await screen.findByRole('button', { name: 'Cancel' });
        await user.click(cancelButton);
        await waitFor(() => {
            expect(cancelAudioJob).toHaveBeenCalledWith('job-123');
        });
        expect(await screen.findByRole('status')).toHaveTextContent('Cancelled');
        expect(MockEventSource.instances[0].closed).toBe(true);
    });
    it('shows summarized text returned by the backend', async () => {
        const user = userEvent.setup();
        render(<App />);
        await user.type(await screen.findByLabelText(/enter text/i), 'Long text');
        await user.click(screen.getByLabelText(/summarize text/i));
        await user.click(screen.getByRole('button', { name: /generate audio/i }));
        await waitFor(() => {
            expect(MockEventSource.instances).toHaveLength(1);
        });
        act(() => {
            MockEventSource.instances[0].emit(createAudioJobStatus({
                job_id: 'job-123',
                status: 'done',
                summarize: true,
                audio_url: '/audios/job-123.wav',
                summarized_text: 'Short summary.',
                error: null,
            }));
        });
        expect(await screen.findByText('Short summary.')).toBeInTheDocument();
    });
    it('generates and renders an editable multi-speaker podcast', async () => {
        const user = userEvent.setup();
        render(<App />);
        await user.click(await screen.findByRole('button', { name: 'Podcast Director' }));
        await user.type(screen.getByLabelText(/source material/i), 'SQLite runs inside an application.');
        await user.click(screen.getByRole('button', { name: 'Generate script' }));
        await waitFor(() => {
            expect(startPodcastWorkflow).toHaveBeenCalledWith({
                text: 'SQLite runs inside an application.',
                format: 'interview',
                duration: 'short',
            });
        });
        expect(await screen.findByDisplayValue('Where does SQLite run?')).toBeInTheDocument();
        expect(screen.getByDisplayValue('Inside the application process.')).toBeInTheDocument();
        expect(screen.getByText('Source review passed')).toBeInTheDocument();
        expect(screen.getByText(/1 source fact checked · 1 automatic revision/i))
            .toBeInTheDocument();
        const guestTurn = screen.getByLabelText('Text for turn 2');
        await user.clear(guestTurn);
        await user.type(guestTurn, 'It runs in the same application process.');
        await user.click(screen.getByRole('button', { name: 'Approve & generate podcast' }));
        await waitFor(() => {
            expect(approvePodcastWorkflow).toHaveBeenCalledWith('workflow-123', {
                script: {
                    title: 'Inside SQLite',
                    segments: [
                        {
                            speaker: 'host',
                            text: 'Where does SQLite run?',
                        },
                        {
                            speaker: 'guest',
                            text: 'It runs in the same application process.',
                        },
                    ],
                },
                language_code: 'a',
                host_voice: 'af_heart',
                guest_voice: 'af_bella',
            });
        });
        expect(createAudioJob).not.toHaveBeenCalled();
        await waitFor(() => {
            expect(MockEventSource.instances).toHaveLength(1);
        });
        act(() => {
            MockEventSource.instances[0].emit(createAudioJobStatus({
                status: 'generating',
                progress: 75,
                audio_url: null,
            }));
        });
        expect(await screen.findByRole('status')).toHaveTextContent('Generating turn 2 of 2 · Guest · 75%');
    });
    it('recovers a pending podcast review after refresh', async () => {
        window.localStorage.setItem('pending-podcast-workflow-id', 'workflow-123');
        render(<App />);
        await waitFor(() => {
            expect(fetchPodcastWorkflow).toHaveBeenCalledWith('workflow-123');
        });
        expect(await screen.findByDisplayValue('Where does SQLite run?')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Podcast Director' })).toHaveAttribute('aria-pressed', 'true');
        expect(screen.getByText('Source review passed')).toBeInTheDocument();
    });
    it('loads recent generations and deletes a confirmed job', async () => {
        const user = userEvent.setup();
        const retainedJob = createAudioJobStatus({
            job_id: 'history-job',
            text_preview: 'Saved episode',
            audio_url: '/audios/history-job.wav',
        });
        vi.mocked(fetchAudioJobs).mockResolvedValue([retainedJob]);
        vi.stubGlobal('confirm', vi.fn(() => true));
        render(<App />);
        expect(await screen.findByText('Saved episode')).toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'Download' })).toHaveAttribute('href', '/api/audio-jobs/history-job/download');
        await user.click(screen.getByRole('button', { name: 'Delete' }));
        await waitFor(() => {
            expect(deleteAudioJob).toHaveBeenCalledWith('history-job');
        });
        expect(screen.queryByText('Saved episode')).not.toBeInTheDocument();
    });
    it('shows job creation API errors', async () => {
        const user = userEvent.setup();
        vi.mocked(createAudioJob).mockRejectedValue(new Error('Could not create audio job'));
        render(<App />);
        await user.type(await screen.findByLabelText(/enter text/i), 'Hello');
        await user.click(screen.getByRole('button', { name: /generate audio/i }));
        expect(await screen.findByRole('alert')).toHaveTextContent('Could not create audio job');
    });
    it('shows streamed job errors', async () => {
        const user = userEvent.setup();
        render(<App />);
        await user.type(await screen.findByLabelText(/enter text/i), 'Hello');
        await user.click(screen.getByRole('button', { name: /generate audio/i }));
        await waitFor(() => {
            expect(MockEventSource.instances).toHaveLength(1);
        });
        act(() => {
            MockEventSource.instances[0].emit(createAudioJobStatus({
                job_id: 'job-123',
                status: 'failed',
                audio_url: null,
                summarized_text: null,
                error: 'Could not generate audio',
            }));
        });
        expect(await screen.findByRole('alert')).toHaveTextContent('Could not generate audio');
    });
});
