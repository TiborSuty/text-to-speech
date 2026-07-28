import type { AppConfig, AudioJobCreateResponse, AudioJobStatusResponse, AudioRequest, AudioResponse, LanguageOption, PodcastScript, PodcastScriptRequest, PodcastWorkflow, PodcastWorkflowApproval, } from './types';
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';
function formatDetail(detail: unknown): string | null {
    if (typeof detail === 'string') {
        return detail;
    }
    if (Array.isArray(detail)) {
        return detail
            .map((item) => {
            if (item && typeof item === 'object' && 'msg' in item) {
                return String(item.msg);
            }
            return null;
        })
            .filter(Boolean)
            .join(', ');
    }
    return null;
}
async function request<T>(path: string, init: RequestInit): Promise<T> {
    const response = await fetch(`${API_BASE_URL}${path}`, init);
    if (!response.ok) {
        let message = `Request failed with status ${response.status}`;
        try {
            const body = await response.json();
            message = formatDetail(body.detail) ?? message;
        }
        catch {
            message = `Request failed with status ${response.status}`;
        }
        throw new Error(message);
    }
    if (response.status === 204) {
        return undefined as T;
    }
    return response.json() as Promise<T>;
}
export function fetchLanguages(): Promise<LanguageOption[]> {
    return request<LanguageOption[]>('/api/languages', {
        headers: { Accept: 'application/json' },
    });
}
export function fetchAppConfig(): Promise<AppConfig> {
    return request<AppConfig>('/api/config', {
        headers: { Accept: 'application/json' },
    });
}
export function generatePodcastScript(payload: PodcastScriptRequest): Promise<PodcastScript> {
    return request<PodcastScript>('/api/podcast-scripts', {
        method: 'POST',
        headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
    });
}
export function startPodcastWorkflow(payload: PodcastScriptRequest): Promise<PodcastWorkflow> {
    return request<PodcastWorkflow>('/api/podcast-workflows', {
        method: 'POST',
        headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
    });
}
export function fetchPodcastWorkflow(workflowId: string): Promise<PodcastWorkflow> {
    return request<PodcastWorkflow>(`/api/podcast-workflows/${workflowId}`, {
        headers: { Accept: 'application/json' },
    });
}
export function approvePodcastWorkflow(workflowId: string, payload: PodcastWorkflowApproval): Promise<AudioJobCreateResponse> {
    return request<AudioJobCreateResponse>(`/api/podcast-workflows/${workflowId}/approve`, {
        method: 'POST',
        headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
    });
}
export function generateAudio(payload: AudioRequest): Promise<AudioResponse> {
    return request<AudioResponse>('/api/audio', {
        method: 'POST',
        headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
    });
}
export function createAudioJob(payload: AudioRequest): Promise<AudioJobCreateResponse> {
    return request<AudioJobCreateResponse>('/api/audio-jobs', {
        method: 'POST',
        headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
    });
}
export function fetchAudioJobs(limit = 20): Promise<AudioJobStatusResponse[]> {
    return request<AudioJobStatusResponse[]>(`/api/audio-jobs?limit=${encodeURIComponent(limit)}`, {
        headers: { Accept: 'application/json' },
    });
}
export function deleteAudioJob(jobId: string): Promise<void> {
    const encodedJobId = encodeURIComponent(jobId);
    return request<void>(`/api/audio-jobs/${encodedJobId}`, {
        method: 'DELETE',
        headers: { Accept: 'application/json' },
    });
}
export function cancelAudioJob(jobId: string): Promise<AudioJobStatusResponse> {
    const encodedJobId = encodeURIComponent(jobId);
    return request<AudioJobStatusResponse>(`/api/audio-jobs/${encodedJobId}/cancel`, {
        method: 'POST',
        headers: { Accept: 'application/json' },
    });
}
export function buildAudioJobEventsUrl(jobId: string): string {
    const encodedJobId = encodeURIComponent(jobId);
    return `${API_BASE_URL}/api/audio-jobs/${encodedJobId}/events`;
}
export function buildAudioJobDownloadUrl(jobId: string): string {
    const encodedJobId = encodeURIComponent(jobId);
    return `${API_BASE_URL}/api/audio-jobs/${encodedJobId}/download`;
}
export function buildAudioUrl(audioUrl: string): string {
    if (/^https?:\/\//.test(audioUrl)) {
        return audioUrl;
    }
    return `${API_BASE_URL}${audioUrl}`;
}
