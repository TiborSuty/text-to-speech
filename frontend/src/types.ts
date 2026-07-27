// Describes one language option returned from the backend.
export type LanguageOption = {
  // Stores the label displayed to the user in the language selector.
  label: string;
  // Stores the Kokoro language code submitted to the API.
  code: string;
};

// Describes the request body sent when the user generates audio.
export type AudioRequest = {
  // Stores the text that should be summarized or converted to speech.
  text: string;
  // Stores the selected language code expected by the backend.
  language_code: string;
  // Stores whether the backend should summarize before generating audio.
  summarize: boolean;
};

// Describes the response returned after audio generation succeeds.
export type AudioResponse = {
  // Stores the URL path or absolute URL for the generated audio file.
  audio_url: string;
  // Stores the optional generated summary returned by the backend.
  summarized_text: string | null;
};

// Lists every status an asynchronous audio job can report.
export type AudioJobStatus = 'queued' | 'summarizing' | 'generating' | 'done' | 'failed';

// Describes the response returned immediately after creating an audio job.
export type AudioJobCreateResponse = {
  // Stores the unique ID used to subscribe to job events.
  job_id: string;
};

// Describes one audio job status payload streamed over SSE.
export type AudioJobStatusResponse = {
  // Stores the unique ID this status belongs to.
  job_id: string;
  // Stores the current lifecycle status for the job.
  status: AudioJobStatus;
  // Stores the generated audio URL once the job completes.
  audio_url: string | null;
  // Stores optional summary text once the job completes.
  summarized_text: string | null;
  // Stores a user-visible failure message when the job fails.
  error: string | null;
};
