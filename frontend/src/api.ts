/// <reference types="vite/client" />

// Imports the TypeScript shapes shared by API request and response helpers.
import type {
  AudioJobCreateResponse,
  AudioRequest,
  AudioResponse,
  LanguageOption,
} from './types';

// Reads an optional backend base URL from Vite environment variables.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

// Converts different FastAPI error-detail formats into one displayable message.
function formatDetail(detail: unknown): string | null {
  // Handles the simple case where the backend sends a plain string detail.
  if (typeof detail === 'string') {
    // Returns the string directly because it is already user-readable.
    return detail;
  }

  // Handles FastAPI validation errors, which usually arrive as an array.
  if (Array.isArray(detail)) {
    // Converts each validation item into its message text when possible.
    return detail
      // Maps every validation object to a message string or null.
      .map((item) => {
        // Checks that the item is an object with the FastAPI "msg" property.
        if (item && typeof item === 'object' && 'msg' in item) {
          // Converts the message value to a string for display.
          return String(item.msg);
        }
        // Ignores array items that do not match FastAPI's validation shape.
        return null;
      })
      // Removes null values from unsupported validation items.
      .filter(Boolean)
      // Joins all validation messages into a single sentence-like string.
      .join(', ');
  }

  // Returns null when the backend detail is not in a supported format.
  return null;
}

// Sends a JSON API request and either returns parsed JSON or throws an Error.
async function request<T>(path: string, init: RequestInit): Promise<T> {
  // Calls the backend using the configured base URL plus the endpoint path.
  const response = await fetch(`${API_BASE_URL}${path}`, init);

  // Treats non-2xx responses as failed requests.
  if (!response.ok) {
    // Creates a fallback error message in case the backend body is unavailable.
    let message = `Request failed with status ${response.status}`;

    // Tries to read and parse the backend's JSON error body.
    try {
      // Parses the error response body.
      const body = await response.json();
      // Uses a formatted backend detail when available, otherwise keeps the fallback.
      message = formatDetail(body.detail) ?? message;
    // Falls back when the response body is not valid JSON.
    } catch {
      // Restores the generic status message after JSON parsing fails.
      message = `Request failed with status ${response.status}`;
    }

    // Throws an Error so React code can show the message in the UI.
    throw new Error(message);
  }

  // Parses and returns the successful response body as the expected type.
  return response.json() as Promise<T>;
}

// Fetches the list of languages supported by the backend.
export function fetchLanguages(): Promise<LanguageOption[]> {
  // Sends a GET-style request by passing only the Accept header.
  return request<LanguageOption[]>('/api/languages', {
    // Asks the backend to return JSON.
    headers: { Accept: 'application/json' },
  });
}

// Sends text-to-speech generation input to the backend.
export function generateAudio(payload: AudioRequest): Promise<AudioResponse> {
  // Sends a POST request to the audio endpoint with a JSON body.
  return request<AudioResponse>('/api/audio', {
    // Uses POST because audio generation changes server-side output files.
    method: 'POST',
    // Sends headers required for JSON request and response bodies.
    headers: {
      // Asks the backend to return JSON.
      Accept: 'application/json',
      // Tells FastAPI that the request body is JSON.
      'Content-Type': 'application/json',
    },
    // Serializes the strongly typed payload into a JSON string.
    body: JSON.stringify(payload),
  });
}

// Starts an asynchronous text-to-speech job on the backend.
export function createAudioJob(payload: AudioRequest): Promise<AudioJobCreateResponse> {
  // Sends a POST request to the async audio-job endpoint with a JSON body.
  return request<AudioJobCreateResponse>('/api/audio-jobs', {
    // Uses POST because a new backend job is created.
    method: 'POST',
    // Sends headers required for JSON request and response bodies.
    headers: {
      // Asks the backend to return JSON.
      Accept: 'application/json',
      // Tells FastAPI that the request body is JSON.
      'Content-Type': 'application/json',
    },
    // Serializes the strongly typed payload into a JSON string.
    body: JSON.stringify(payload),
  });
}

// Builds the EventSource URL for an asynchronous audio job.
export function buildAudioJobEventsUrl(jobId: string): string {
  // Encodes the job ID so it is safe inside a URL path segment.
  const encodedJobId = encodeURIComponent(jobId);
  // Returns the fully resolved SSE endpoint URL.
  return `${API_BASE_URL}/api/audio-jobs/${encodedJobId}/events`;
}

// Builds a browser-usable audio URL from the URL returned by the backend.
export function buildAudioUrl(audioUrl: string): string {
  // Leaves absolute URLs untouched so deployed backends can return full URLs.
  if (/^https?:\/\//.test(audioUrl)) {
    // Returns the absolute URL exactly as the backend provided it.
    return audioUrl;
  }

  // Prefixes relative backend audio paths with the configured API base URL.
  return `${API_BASE_URL}${audioUrl}`;
}
