import { afterEach, describe, expect, it, vi } from 'vitest';
import { buildAudioJobDownloadUrl, buildAudioJobEventsUrl, buildAudioUrl, approvePodcastWorkflow, cancelAudioJob, createAudioJob, deleteAudioJob, fetchAppConfig, fetchAudioJobs, fetchLanguages, fetchPodcastWorkflow, generateAudio, generatePodcastScript, startPodcastWorkflow, } from './api';
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
    it('fetches app configuration', async () => {
        const fetchMock = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => ({ max_text_characters: 50000 }),
        });
        vi.stubGlobal('fetch', fetchMock);
        const result = await fetchAppConfig();
        expect(fetchMock).toHaveBeenCalledWith('/api/config', {
            headers: { Accept: 'application/json' },
        });
        expect(result).toEqual({ max_text_characters: 50000 });
    });
    it('generates a structured podcast script', async () => {
        const generatedScript = {
            title: 'Inside SQLite',
            segments: [
                { speaker: 'host' as const, text: 'Where does SQLite run?' },
                { speaker: 'guest' as const, text: 'Inside the application.' },
            ],
        };
        const fetchMock = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => generatedScript,
        });
        vi.stubGlobal('fetch', fetchMock);
        const payload = {
            text: 'SQLite source material',
            format: 'interview' as const,
            duration: 'short' as const,
        };
        const result = await generatePodcastScript(payload);
        expect(fetchMock).toHaveBeenCalledWith('/api/podcast-scripts', {
            method: 'POST',
            headers: {
                Accept: 'application/json',
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload),
        });
        expect(result).toEqual(generatedScript);
    });
    it('starts a grounded podcast workflow', async () => {
        const workflow = {
            workflow_id: 'workflow-123',
            status: 'awaiting_review' as const,
            script: {
                title: 'Inside SQLite',
                segments: [{ speaker: 'host' as const, text: 'SQLite is embedded.' }],
            },
            facts: ['SQLite runs in the application process.'],
            issues: [],
            revision_count: 0,
            audio_job_id: null,
        };
        const fetchMock = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => workflow,
        });
        vi.stubGlobal('fetch', fetchMock);
        const payload = {
            text: 'SQLite source material',
            format: 'narration' as const,
            duration: 'short' as const,
        };
        const result = await startPodcastWorkflow(payload);
        expect(fetchMock).toHaveBeenCalledWith('/api/podcast-workflows', {
            method: 'POST',
            headers: {
                Accept: 'application/json',
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload),
        });
        expect(result).toEqual(workflow);
    });
    it('approves a podcast workflow', async () => {
        const fetchMock = vi.fn().mockResolvedValue({
            ok: true,
            status: 202,
            json: async () => ({ job_id: 'workflow-123' }),
        });
        vi.stubGlobal('fetch', fetchMock);
        const approval = {
            script: {
                title: 'Inside SQLite',
                segments: [{ speaker: 'host' as const, text: 'SQLite is embedded.' }],
            },
            language_code: 'a',
            host_voice: 'af_heart',
            guest_voice: 'af_bella',
            audio_format: 'wav' as const,
        };
        const result = await approvePodcastWorkflow('workflow-123', approval);
        expect(fetchMock).toHaveBeenCalledWith('/api/podcast-workflows/workflow-123/approve', {
            method: 'POST',
            headers: {
                Accept: 'application/json',
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(approval),
        });
        expect(result).toEqual({ job_id: 'workflow-123' });
    });
    it('fetches a persisted podcast workflow', async () => {
        const workflow = {
            workflow_id: 'workflow-123',
            status: 'awaiting_review' as const,
            script: {
                title: 'Recovered',
                segments: [{ speaker: 'host' as const, text: 'Recovered turn.' }],
            },
            facts: ['Recovered fact.'],
            issues: [],
            revision_count: 0,
            audio_job_id: null,
        };
        const fetchMock = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => workflow,
        });
        vi.stubGlobal('fetch', fetchMock);
        const result = await fetchPodcastWorkflow('workflow-123');
        expect(fetchMock).toHaveBeenCalledWith('/api/podcast-workflows/workflow-123', { headers: { Accept: 'application/json' } });
        expect(result).toEqual(workflow);
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
            voice: 'af_heart',
            summarize: false,
            audio_format: 'wav',
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
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
            ok: false,
            status: 500,
            json: async () => ({ detail: 'Could not generate audio' }),
        }));
        await expect(generateAudio({
            text: 'Hello',
            language_code: 'a',
            voice: 'af_heart',
            summarize: false,
            audio_format: 'wav',
        })).rejects.toThrow('Could not generate audio');
    });
    it('posts async audio job requests', async () => {
        const fetchMock = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => ({ job_id: 'job-123' }),
        });
        vi.stubGlobal('fetch', fetchMock);
        const payload: AudioRequest = {
            text: 'Hello',
            language_code: 'a',
            voice: 'af_heart',
            summarize: false,
            audio_format: 'mp3',
        };
        const result = await createAudioJob(payload);
        expect(fetchMock).toHaveBeenCalledWith('/api/audio-jobs', {
            method: 'POST',
            headers: {
                Accept: 'application/json',
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload),
        });
        expect(result).toEqual({ job_id: 'job-123' });
    });
    it('fetches recent audio jobs', async () => {
        const fetchMock = vi.fn().mockResolvedValue({
            ok: true,
            status: 200,
            json: async () => [],
        });
        vi.stubGlobal('fetch', fetchMock);
        const result = await fetchAudioJobs(12);
        expect(fetchMock).toHaveBeenCalledWith('/api/audio-jobs?limit=12', {
            headers: { Accept: 'application/json' },
        });
        expect(result).toEqual([]);
    });
    it('deletes an audio job', async () => {
        const fetchMock = vi.fn().mockResolvedValue({
            ok: true,
            status: 204,
        });
        vi.stubGlobal('fetch', fetchMock);
        await expect(deleteAudioJob('job 123')).resolves.toBeUndefined();
        expect(fetchMock).toHaveBeenCalledWith('/api/audio-jobs/job%20123', {
            method: 'DELETE',
            headers: { Accept: 'application/json' },
        });
    });
    it('cancels an audio job', async () => {
        const cancelledJob = {
            job_id: 'job 123',
            status: 'cancelled',
            queue_position: null,
            progress: 0,
        };
        const fetchMock = vi.fn().mockResolvedValue({
            ok: true,
            status: 200,
            json: async () => cancelledJob,
        });
        vi.stubGlobal('fetch', fetchMock);
        await expect(cancelAudioJob('job 123')).resolves.toEqual(cancelledJob);
        expect(fetchMock).toHaveBeenCalledWith('/api/audio-jobs/job%20123/cancel', {
            method: 'POST',
            headers: { Accept: 'application/json' },
        });
    });
    it('builds audio job event stream URLs', () => {
        expect(buildAudioJobEventsUrl('job 123')).toBe('/api/audio-jobs/job%20123/events');
    });
    it('builds audio job download URLs', () => {
        expect(buildAudioJobDownloadUrl('job 123')).toBe('/api/audio-jobs/job%20123/download');
    });
    it('keeps relative audio URLs relative when no API base URL is configured', () => {
        expect(buildAudioUrl('/audios/audio.wav')).toBe('/audios/audio.wav');
    });
});
