export type VoiceOption = {
    id: string;
    label: string;
};
export type LanguageOption = {
    label: string;
    code: string;
    default_voice: string;
    voices: VoiceOption[];
};
export type AppConfig = {
    max_text_characters: number;
};
export type AudioFormat = 'wav' | 'mp3' | 'flac' | 'ogg';
export type PodcastFormat = 'narration' | 'interview' | 'explainer';
export type PodcastDuration = 'short' | 'medium' | 'long';
export type PodcastSpeaker = 'host' | 'guest';
export type PodcastScriptSegment = {
    speaker: PodcastSpeaker;
    text: string;
};
export type PodcastScriptRequest = {
    text: string;
    format: PodcastFormat;
    duration: PodcastDuration;
};
export type PodcastScript = {
    title: string;
    segments: PodcastScriptSegment[];
};
export type PodcastWorkflow = {
    workflow_id: string;
    status: 'awaiting_review' | 'approved' | 'queued';
    script: PodcastScript;
    facts: string[];
    issues: string[];
    revision_count: number;
    audio_job_id: string | null;
};
export type PodcastWorkflowApproval = {
    script: PodcastScript;
    language_code: string;
    host_voice: string;
    guest_voice: string;
    audio_format: AudioFormat;
};
export type AudioSegment = PodcastScriptSegment & {
    voice: string;
};
export type AudioRequest = {
    text: string;
    language_code: string;
    voice: string;
    summarize: boolean;
    audio_format: AudioFormat;
    segments?: AudioSegment[];
};
export type AudioResponse = {
    audio_url: string;
    summarized_text: string | null;
};
export type AudioJobStatus = 'queued' | 'summarizing' | 'generating' | 'cancel_requested' | 'cancelled' | 'done' | 'failed';
export type AudioJobCreateResponse = {
    job_id: string;
};
export type AudioJobStatusResponse = {
    job_id: string;
    status: AudioJobStatus;
    queue_position: number | null;
    progress: number;
    language_code: string;
    voice: string;
    summarize: boolean;
    audio_format: AudioFormat;
    text_preview: string;
    created_at: string;
    updated_at: string;
    audio_url: string | null;
    summarized_text: string | null;
    error: string | null;
};
