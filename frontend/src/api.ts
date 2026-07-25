/// <reference types="vite/client" />

import type { AudioRequest, AudioResponse, LanguageOption } from './types';

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
    } catch {
      message = `Request failed with status ${response.status}`;
    }

    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

export function fetchLanguages(): Promise<LanguageOption[]> {
  return request<LanguageOption[]>('/api/languages', {
    headers: { Accept: 'application/json' },
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

export function buildAudioUrl(audioUrl: string): string {
  if (/^https?:\/\//.test(audioUrl)) {
    return audioUrl;
  }

  return `${API_BASE_URL}${audioUrl}`;
}
