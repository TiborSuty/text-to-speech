import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import './App.css';
import { buildAudioJobDownloadUrl, buildAudioJobEventsUrl, buildAudioUrl, approvePodcastWorkflow, cancelAudioJob, createAudioJob, deleteAudioJob, fetchAppConfig, fetchAudioJobs, fetchLanguages, fetchPodcastWorkflow, startPodcastWorkflow, } from './api';
import type { AudioJobStatus, AudioJobStatusResponse, AudioSegment, LanguageOption, PodcastDuration, PodcastFormat, PodcastScript, PodcastScriptSegment, } from './types';
function getInitialLanguage(languages: LanguageOption[]): LanguageOption | null {
    return languages.find((language) => language.code === 'a') ?? languages[0] ?? null;
}
function parseAudioJobEvent(data: string): AudioJobStatusResponse | null {
    try {
        return JSON.parse(data) as AudioJobStatusResponse;
    }
    catch {
        return null;
    }
}
function isActiveAudioJobStatus(status: AudioJobStatus | null): boolean {
    return (status === 'queued'
        || status === 'summarizing'
        || status === 'generating'
        || status === 'cancel_requested');
}
type CreationMode = 'speech' | 'podcast';
const PENDING_PODCAST_WORKFLOW_KEY = 'pending-podcast-workflow-id';
function getGuestVoice(language: LanguageOption | null): string {
    if (!language) {
        return '';
    }
    return (language.voices.find((voice) => voice.id !== language.default_voice)?.id
        ?? language.default_voice);
}
function getPodcastGenerationStatus(segments: PodcastScriptSegment[], progress: number): string | null {
    if (segments.length === 0) {
        return null;
    }
    const totalCharacters = segments.reduce((total, segment) => total + segment.text.length, 0);
    const processedCharacters = totalCharacters * progress / 100;
    let cumulativeCharacters = 0;
    const currentSegmentIndex = segments.findIndex((segment) => {
        cumulativeCharacters += segment.text.length;
        return processedCharacters <= cumulativeCharacters;
    });
    const resolvedIndex = currentSegmentIndex === -1
        ? segments.length - 1
        : currentSegmentIndex;
    const speaker = segments[resolvedIndex].speaker === 'host' ? 'Host' : 'Guest';
    return `Generating turn ${resolvedIndex + 1} of ${segments.length} · ${speaker} · ${progress}%`;
}
function getGenerationStatus(jobStatus: AudioJobStatus | null, queuePosition: number | null, progress: number, resolvedAudioUrl: string | null): string {
    if (jobStatus === 'queued') {
        return queuePosition ? `Queued · Position ${queuePosition}` : 'Queued';
    }
    if (jobStatus === 'summarizing') {
        return 'Summarizing text';
    }
    if (jobStatus === 'generating') {
        return `Generating audio · ${progress}%`;
    }
    if (jobStatus === 'cancel_requested') {
        return 'Cancelling';
    }
    if (jobStatus === 'cancelled') {
        return 'Cancelled';
    }
    if (resolvedAudioUrl) {
        return 'Audio ready';
    }
    return '';
}
const HISTORY_LIMIT = 20;
const DEFAULT_MAX_TEXT_CHARACTERS = 50000;
const jobDateFormatter = new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
});
function formatJobDate(timestamp: string): string {
    const date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) {
        return 'Unknown time';
    }
    return jobDateFormatter.format(date);
}
function upsertAudioJob(currentJobs: AudioJobStatusResponse[], nextJob: AudioJobStatusResponse): AudioJobStatusResponse[] {
    const remainingJobs = currentJobs.filter((job) => job.job_id !== nextJob.job_id);
    return [nextJob, ...remainingJobs]
        .sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at))
        .slice(0, HISTORY_LIMIT);
}
export default function App() {
    const [creationMode, setCreationMode] = useState<CreationMode>('speech');
    const [languages, setLanguages] = useState<LanguageOption[]>([]);
    const [languageCode, setLanguageCode] = useState('');
    const [voice, setVoice] = useState('');
    const [text, setText] = useState('');
    const [summarize, setSummarize] = useState(false);
    const [podcastFormat, setPodcastFormat] = useState<PodcastFormat>('interview');
    const [podcastDuration, setPodcastDuration] = useState<PodcastDuration>('short');
    const [guestVoice, setGuestVoice] = useState('');
    const [podcastScript, setPodcastScript] = useState<PodcastScript | null>(null);
    const [podcastWorkflowId, setPodcastWorkflowId] = useState<string | null>(null);
    const [podcastFacts, setPodcastFacts] = useState<string[]>([]);
    const [podcastIssues, setPodcastIssues] = useState<string[]>([]);
    const [podcastRevisionCount, setPodcastRevisionCount] = useState(0);
    const [isGeneratingScript, setIsGeneratingScript] = useState(false);
    const [scriptError, setScriptError] = useState<string | null>(null);
    const [activePodcastSegments, setActivePodcastSegments] = useState<PodcastScriptSegment[]>([]);
    const [audioUrl, setAudioUrl] = useState<string | null>(null);
    const [summarizedText, setSummarizedText] = useState<string | null>(null);
    const [isLoadingLanguages, setIsLoadingLanguages] = useState(true);
    const [jobStatus, setJobStatus] = useState<AudioJobStatus | null>(null);
    const [currentJobId, setCurrentJobId] = useState<string | null>(null);
    const [queuePosition, setQueuePosition] = useState<number | null>(null);
    const [jobProgress, setJobProgress] = useState(0);
    const [maxTextCharacters, setMaxTextCharacters] = useState(DEFAULT_MAX_TEXT_CHARACTERS);
    const [cancellingJobId, setCancellingJobId] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [streamNotice, setStreamNotice] = useState<string | null>(null);
    const [audioJobs, setAudioJobs] = useState<AudioJobStatusResponse[]>([]);
    const [isLoadingHistory, setIsLoadingHistory] = useState(true);
    const [historyError, setHistoryError] = useState<string | null>(null);
    const [deletingJobId, setDeletingJobId] = useState<string | null>(null);
    const audioEventsRef = useRef<EventSource | null>(null);
    const trimmedText = text.trim();
    const selectedLanguage = languages.find((language) => language.code === languageCode);
    const isGenerating = isActiveAudioJobStatus(jobStatus);
    const podcastScriptText = podcastScript?.segments
        .map((segment) => segment.text.trim())
        .filter(Boolean)
        .join('\n') ?? '';
    const podcastJobText = podcastScript
        ? [podcastScript.title.trim(), podcastScriptText].filter(Boolean).join('\n')
        : '';
    const hasValidPodcastScript = Boolean(podcastScript
        && podcastScript.title.trim()
        && podcastScript.segments.length > 0
        && podcastScript.segments.every((segment) => Boolean(segment.text.trim()))
        && podcastJobText.length <= maxTextCharacters);
    const canGenerate = (creationMode === 'speech'
        ? Boolean(trimmedText) && trimmedText.length <= maxTextCharacters
        : hasValidPodcastScript && Boolean(podcastWorkflowId))
        && Boolean(languageCode)
        && Boolean(voice)
        && (creationMode === 'speech' || Boolean(guestVoice))
        && !isGeneratingScript
        && !isGenerating;
    const resolvedAudioUrl = useMemo(() => (audioUrl ? buildAudioUrl(audioUrl) : null), [audioUrl]);
    const generationStatus = (jobStatus === 'generating'
        && activePodcastSegments.length > 0)
        ? getPodcastGenerationStatus(activePodcastSegments, jobProgress)
        : getGenerationStatus(jobStatus, queuePosition, jobProgress, resolvedAudioUrl);
    const displayedGenerationStatus = streamNotice ?? generationStatus;
    useEffect(() => {
        let isMounted = true;
        fetchAppConfig()
            .then((config) => {
            if (isMounted) {
                setMaxTextCharacters(config.max_text_characters);
            }
        })
            .catch(() => undefined);
        return () => {
            isMounted = false;
        };
    }, []);
    useEffect(() => {
        const pendingWorkflowId = window.localStorage.getItem(PENDING_PODCAST_WORKFLOW_KEY);
        if (!pendingWorkflowId) {
            return undefined;
        }
        let isMounted = true;
        fetchPodcastWorkflow(pendingWorkflowId)
            .then((workflow) => {
            if (!isMounted) {
                return;
            }
            if (workflow.status !== 'awaiting_review') {
                window.localStorage.removeItem(PENDING_PODCAST_WORKFLOW_KEY);
                return;
            }
            setCreationMode('podcast');
            setPodcastWorkflowId(workflow.workflow_id);
            setPodcastScript(workflow.script);
            setPodcastFacts(workflow.facts);
            setPodcastIssues(workflow.issues);
            setPodcastRevisionCount(workflow.revision_count);
        })
            .catch(() => undefined);
        return () => {
            isMounted = false;
        };
    }, []);
    useEffect(() => {
        let isMounted = true;
        async function loadLanguages() {
            try {
                const options = await fetchLanguages();
                if (!isMounted) {
                    return;
                }
                setLanguages(options);
                const initialLanguage = getInitialLanguage(options);
                setLanguageCode(initialLanguage?.code ?? '');
                setVoice(initialLanguage?.default_voice ?? '');
                setGuestVoice(getGuestVoice(initialLanguage));
            }
            catch (loadError) {
                if (!isMounted) {
                    return;
                }
                setError(loadError instanceof Error
                    ? loadError.message
                    : 'Could not load supported languages');
            }
            finally {
                if (isMounted) {
                    setIsLoadingLanguages(false);
                }
            }
        }
        loadLanguages();
        return () => {
            isMounted = false;
        };
    }, []);
    useEffect(() => {
        let isMounted = true;
        async function loadAudioJobs() {
            try {
                const jobs = await fetchAudioJobs(HISTORY_LIMIT);
                if (!isMounted) {
                    return;
                }
                setAudioJobs((currentJobs) => jobs.reduce((mergedJobs, job) => upsertAudioJob(mergedJobs, job), currentJobs));
            }
            catch (loadError) {
                if (!isMounted) {
                    return;
                }
                setHistoryError(loadError instanceof Error
                    ? loadError.message
                    : 'Could not load recent generations');
            }
            finally {
                if (isMounted) {
                    setIsLoadingHistory(false);
                }
            }
        }
        loadAudioJobs();
        return () => {
            isMounted = false;
        };
    }, []);
    function handleLanguageChange(nextLanguageCode: string) {
        const nextLanguage = languages.find((language) => language.code === nextLanguageCode);
        setLanguageCode(nextLanguageCode);
        setVoice(nextLanguage?.default_voice ?? '');
        setGuestVoice(getGuestVoice(nextLanguage ?? null));
    }
    function invalidatePodcastWorkflow() {
        window.localStorage.removeItem(PENDING_PODCAST_WORKFLOW_KEY);
        setPodcastWorkflowId(null);
        setPodcastScript(null);
        setPodcastFacts([]);
        setPodcastIssues([]);
        setPodcastRevisionCount(0);
        setScriptError(null);
    }
    async function handleGeneratePodcastScript() {
        if (!trimmedText
            || trimmedText.length > maxTextCharacters
            || isGeneratingScript
            || isGenerating) {
            return;
        }
        setIsGeneratingScript(true);
        setScriptError(null);
        try {
            const workflow = await startPodcastWorkflow({
                text: trimmedText,
                format: podcastFormat,
                duration: podcastDuration,
            });
            setPodcastWorkflowId(workflow.workflow_id);
            window.localStorage.setItem(PENDING_PODCAST_WORKFLOW_KEY, workflow.workflow_id);
            setPodcastScript(workflow.script);
            setPodcastFacts(workflow.facts);
            setPodcastIssues(workflow.issues);
            setPodcastRevisionCount(workflow.revision_count);
        }
        catch (generateScriptError) {
            setScriptError(generateScriptError instanceof Error
                ? generateScriptError.message
                : 'Could not generate podcast script');
        }
        finally {
            setIsGeneratingScript(false);
        }
    }
    function updatePodcastSegment(segmentIndex: number, update: Partial<PodcastScriptSegment>) {
        setPodcastScript((currentScript) => {
            if (!currentScript) {
                return currentScript;
            }
            return {
                ...currentScript,
                segments: currentScript.segments.map((segment, index) => index === segmentIndex ? { ...segment, ...update } : segment),
            };
        });
    }
    function addPodcastSegment() {
        setPodcastScript((currentScript) => {
            if (!currentScript || currentScript.segments.length >= 24) {
                return currentScript;
            }
            const lastSpeaker = currentScript.segments.at(-1)?.speaker ?? 'guest';
            return {
                ...currentScript,
                segments: [
                    ...currentScript.segments,
                    {
                        speaker: lastSpeaker === 'host' ? 'guest' : 'host',
                        text: '',
                    },
                ],
            };
        });
    }
    function removePodcastSegment(segmentIndex: number) {
        setPodcastScript((currentScript) => {
            if (!currentScript || currentScript.segments.length <= 1) {
                return currentScript;
            }
            return {
                ...currentScript,
                segments: currentScript.segments.filter((_segment, index) => index !== segmentIndex),
            };
        });
    }
    useEffect(() => {
        return () => {
            audioEventsRef.current?.close();
            audioEventsRef.current = null;
        };
    }, []);
    async function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (!canGenerate) {
            return;
        }
        audioEventsRef.current?.close();
        audioEventsRef.current = null;
        setJobStatus('queued');
        setQueuePosition(null);
        setJobProgress(0);
        setCurrentJobId(null);
        setError(null);
        setStreamNotice(null);
        setAudioUrl(null);
        setSummarizedText(null);
        try {
            const podcastSegments: AudioSegment[] | undefined = (creationMode === 'podcast' && podcastScript)
                ? podcastScript.segments.map((segment) => ({
                    speaker: segment.speaker,
                    text: segment.text.trim(),
                    voice: segment.speaker === 'host' ? voice : guestVoice,
                }))
                : undefined;
            setActivePodcastSegments(podcastSegments?.map(({ speaker, text: segmentText }) => ({
                speaker,
                text: segmentText,
            })) ?? []);
            const response = (creationMode === 'podcast'
                && podcastScript
                && podcastWorkflowId)
                ? await approvePodcastWorkflow(podcastWorkflowId, {
                    script: podcastScript,
                    language_code: languageCode,
                    host_voice: voice,
                    guest_voice: guestVoice,
                })
                : await createAudioJob({
                    text: trimmedText,
                    language_code: languageCode,
                    voice,
                    summarize,
                });
            if (creationMode === 'podcast') {
                window.localStorage.removeItem(PENDING_PODCAST_WORKFLOW_KEY);
            }
            setCurrentJobId(response.job_id);
            const eventSource = new EventSource(buildAudioJobEventsUrl(response.job_id));
            audioEventsRef.current = eventSource;
            eventSource.onmessage = (message) => {
                const job = parseAudioJobEvent(message.data);
                if (!job) {
                    setJobStatus('failed');
                    setStreamNotice(null);
                    setError('Could not read audio job update');
                    eventSource.close();
                    if (audioEventsRef.current === eventSource) {
                        audioEventsRef.current = null;
                    }
                    return;
                }
                setStreamNotice(null);
                setJobStatus(job.status);
                setQueuePosition(job.queue_position);
                setJobProgress(job.progress);
                setAudioJobs((currentJobs) => upsertAudioJob(currentJobs, job));
                if (job.status === 'done') {
                    if (job.audio_url) {
                        setAudioUrl(job.audio_url);
                        setSummarizedText(job.summarized_text);
                    }
                    else {
                        setError('Audio job finished without an audio URL');
                        setJobStatus('failed');
                    }
                    eventSource.close();
                    if (audioEventsRef.current === eventSource) {
                        audioEventsRef.current = null;
                    }
                    setCurrentJobId(null);
                }
                if (job.status === 'failed') {
                    setError(job.error ?? 'Could not generate audio');
                    eventSource.close();
                    if (audioEventsRef.current === eventSource) {
                        audioEventsRef.current = null;
                    }
                    setCurrentJobId(null);
                }
                if (job.status === 'cancelled') {
                    setAudioUrl(null);
                    setSummarizedText(null);
                    eventSource.close();
                    if (audioEventsRef.current === eventSource) {
                        audioEventsRef.current = null;
                    }
                    setCurrentJobId(null);
                }
            };
            eventSource.onopen = () => {
                if (audioEventsRef.current !== eventSource) {
                    return;
                }
                setStreamNotice(null);
            };
            eventSource.onerror = () => {
                if (audioEventsRef.current !== eventSource) {
                    return;
                }
                setStreamNotice('Connection lost · Reconnecting');
            };
        }
        catch (generateError) {
            setJobStatus(null);
            setCurrentJobId(null);
            setQueuePosition(null);
            setJobProgress(0);
            setStreamNotice(null);
            setError(generateError instanceof Error
                ? generateError.message
                : 'Could not generate audio');
        }
    }
    async function handleCancelJob(jobId: string, primaryJob = false) {
        if (cancellingJobId === jobId) {
            return;
        }
        setCancellingJobId(jobId);
        if (primaryJob) {
            setError(null);
        }
        else {
            setHistoryError(null);
        }
        try {
            const job = await cancelAudioJob(jobId);
            setAudioJobs((currentJobs) => upsertAudioJob(currentJobs, job));
            if (jobId === currentJobId) {
                setJobStatus(job.status);
                setQueuePosition(job.queue_position);
                setJobProgress(job.progress);
                if (job.status === 'cancelled') {
                    audioEventsRef.current?.close();
                    audioEventsRef.current = null;
                    setStreamNotice(null);
                    setCurrentJobId(null);
                }
            }
        }
        catch (cancelError) {
            const message = cancelError instanceof Error
                ? cancelError.message
                : 'Could not cancel audio job';
            if (primaryJob) {
                setError(message);
            }
            else {
                setHistoryError(message);
            }
        }
        finally {
            setCancellingJobId((activeId) => activeId === jobId ? null : activeId);
        }
    }
    async function handleDeleteJob(job: AudioJobStatusResponse) {
        const confirmed = window.confirm(`Delete the audio for "${job.text_preview}"?`);
        if (!confirmed) {
            return;
        }
        setDeletingJobId(job.job_id);
        setHistoryError(null);
        try {
            await deleteAudioJob(job.job_id);
            setAudioJobs((currentJobs) => currentJobs.filter((currentJob) => currentJob.job_id !== job.job_id));
            if (job.audio_url && job.audio_url === audioUrl) {
                setAudioUrl(null);
                setSummarizedText(null);
                setJobStatus(null);
            }
        }
        catch (deleteError) {
            setHistoryError(deleteError instanceof Error
                ? deleteError.message
                : 'Could not delete audio job');
        }
        finally {
            setDeletingJobId(null);
        }
    }
    return (<main className="app-shell">

      <section className="tool-panel" aria-labelledby="app-title">

        <div className="title-block">

          <p className="eyebrow">Text to speech</p>

          <h1 id="app-title">AI Podcaster</h1>
        </div>


        <div className="creation-mode" role="group" aria-label="Creation mode">

          <button className={creationMode === 'speech' ? 'creation-mode-active' : ''} type="button" aria-pressed={creationMode === 'speech'} disabled={isGenerating || isGeneratingScript} onClick={() => setCreationMode('speech')}>
            Text to speech
          </button>

          <button className={creationMode === 'podcast' ? 'creation-mode-active' : ''} type="button" aria-pressed={creationMode === 'podcast'} disabled={isGenerating || isGeneratingScript} onClick={() => setCreationMode('podcast')}>
            Podcast Director
          </button>
        </div>


        <form className="generator-form" onSubmit={handleSubmit}>

          {creationMode === 'podcast' ? (<fieldset className="director-brief">

              <legend>Creative direction</legend>

              <div className="director-controls">

                <label className="field">
                  <span>Format</span>
                  <select value={podcastFormat} disabled={isGenerating || isGeneratingScript} onChange={(event) => {
                setPodcastFormat(event.target.value as PodcastFormat);
                invalidatePodcastWorkflow();
            }}>
                    <option value="narration">Narration</option>
                    <option value="interview">Interview</option>
                    <option value="explainer">Explainer</option>
                  </select>
                </label>

                <label className="field">
                  <span>Episode length</span>
                  <select value={podcastDuration} disabled={isGenerating || isGeneratingScript} onChange={(event) => {
                setPodcastDuration(event.target.value as PodcastDuration);
                invalidatePodcastWorkflow();
            }}>
                    <option value="short">Short · 2–3 min</option>
                    <option value="medium">Medium · 4–6 min</option>
                    <option value="long">Long · 7–10 min</option>
                  </select>
                </label>
              </div>
            </fieldset>) : null}


          <label className="field">

            <span>Select a language</span>

            <select id="language" name="language" autoComplete="off" value={languageCode} onChange={(event) => handleLanguageChange(event.target.value)} disabled={isLoadingLanguages || isGenerating}>

              {languages.map((language) => (<option key={language.code} value={language.code}>

                  {language.label}
                </option>))}
            </select>
          </label>


          <div className={creationMode === 'podcast' ? 'voice-grid' : undefined}>

            <label className="field">

              <span>{creationMode === 'podcast' ? 'Host voice' : 'Select a voice'}</span>

              <select id="voice" name="voice" autoComplete="off" value={voice} onChange={(event) => setVoice(event.target.value)} disabled={isLoadingLanguages || isGenerating || isGeneratingScript}>

                {selectedLanguage?.voices.map((voiceOption) => (<option key={voiceOption.id} value={voiceOption.id}>
                    {voiceOption.label}
                  </option>))}
              </select>
            </label>


            {creationMode === 'podcast' ? (<label className="field">
                <span>Guest voice</span>
                <select id="guest-voice" name="guest-voice" autoComplete="off" value={guestVoice} onChange={(event) => setGuestVoice(event.target.value)} disabled={isLoadingLanguages || isGenerating || isGeneratingScript}>
                  {selectedLanguage?.voices.map((voiceOption) => (<option key={voiceOption.id} value={voiceOption.id}>
                      {voiceOption.label}
                    </option>))}
                </select>
              </label>) : null}
          </div>


          <label className="field">

            <span className="field-heading">

              <span>
                {creationMode === 'podcast' ? 'Source material' : 'Enter text'}
              </span>

              <span className="character-count">
                {text.length.toLocaleString()} / {maxTextCharacters.toLocaleString()}
              </span>
            </span>

            <textarea id="text" name="text" autoComplete="off" value={text} onChange={(event) => {
            setText(event.target.value);
            if (creationMode === 'podcast') {
                invalidatePodcastWorkflow();
            }
        }} maxLength={maxTextCharacters} rows={10} disabled={isGenerating || isGeneratingScript}/>
          </label>


          {creationMode === 'podcast' ? (<section className="script-workspace" aria-labelledby="script-workspace-title">

              <div className="script-workspace-heading">
                <div>
                  <p className="script-kicker">Local AI script desk</p>
                  <h2 id="script-workspace-title">
                    {podcastScript ? 'Edit the conversation' : 'Build the conversation'}
                  </h2>
                </div>

                <button className="generate-script" type="button" disabled={!trimmedText
                || trimmedText.length > maxTextCharacters
                || isGeneratingScript
                || isGenerating} onClick={handleGeneratePodcastScript}>
                  {isGeneratingScript
                ? 'Writing script'
                : podcastScript
                    ? 'Regenerate script'
                    : 'Generate script'}
                </button>
              </div>


              {scriptError ? (<p className="script-error" role="alert">{scriptError}</p>) : null}


              {podcastWorkflowId ? (<aside className={`grounding-review ${podcastIssues.length > 0 ? 'grounding-review-warning' : ''}`} aria-label="Source grounding review">
                  <div className="grounding-review-heading">
                    <strong>
                      {podcastIssues.length > 0
                    ? 'Human review needed'
                    : 'Source review passed'}
                    </strong>
                    <span>
                      {podcastFacts.length} source fact
                      {podcastFacts.length === 1 ? '' : 's'} checked
                      {podcastRevisionCount > 0
                    ? ` · ${podcastRevisionCount} automatic ${podcastRevisionCount === 1 ? 'revision' : 'revisions'}`
                    : ''}
                    </span>
                  </div>


                  {podcastIssues.length > 0 ? (<ul className="grounding-issues">
                      {podcastIssues.map((issue, issueIndex) => (<li key={`${issueIndex}-${issue}`}>{issue}</li>))}
                    </ul>) : null}


                  <details className="grounding-facts">
                    <summary>View extracted facts</summary>
                    <ul>
                      {podcastFacts.map((fact, factIndex) => (<li key={`${factIndex}-${fact}`}>{fact}</li>))}
                    </ul>
                  </details>
                </aside>) : null}


              {podcastScript ? (<div className="script-editor">

                  <label className="field script-title-field">
                    <span>Episode title</span>
                    <input type="text" value={podcastScript.title} maxLength={160} disabled={isGenerating} onChange={(event) => setPodcastScript({
                    ...podcastScript,
                    title: event.target.value,
                })}/>
                  </label>


                  <div className="script-turns">
                    {podcastScript.segments.map((segment, segmentIndex) => (<article className="script-turn" data-speaker={segment.speaker} key={`${segmentIndex}-${segment.speaker}`}>

                        <div className="script-turn-heading">
                          <span className="turn-number">
                            Turn {segmentIndex + 1}
                          </span>
                          <select aria-label={`Speaker for turn ${segmentIndex + 1}`} value={segment.speaker} disabled={isGenerating} onChange={(event) => updatePodcastSegment(segmentIndex, {
                        speaker: event.target.value as 'host' | 'guest',
                    })}>
                            <option value="host">Host</option>
                            <option value="guest">Guest</option>
                          </select>
                          <button className="remove-turn" type="button" aria-label={`Remove turn ${segmentIndex + 1}`} disabled={isGenerating || podcastScript.segments.length <= 1} onClick={() => removePodcastSegment(segmentIndex)}>
                            Remove
                          </button>
                        </div>

                        <textarea className="script-turn-text" aria-label={`Text for turn ${segmentIndex + 1}`} value={segment.text} maxLength={10000} rows={4} disabled={isGenerating} onChange={(event) => updatePodcastSegment(segmentIndex, {
                        text: event.target.value,
                    })}/>
                      </article>))}
                  </div>


                  <button className="add-turn" type="button" disabled={isGenerating || podcastScript.segments.length >= 24} onClick={addPodcastSegment}>
                    Add turn
                  </button>
                </div>) : (<p className="script-empty">
                  Generate a draft, then edit every host and guest turn before recording.
                </p>)}
            </section>) : (<label className="checkbox-row">
              <input type="checkbox" id="summarize" name="summarize" checked={summarize} onChange={(event) => setSummarize(event.target.checked)} disabled={isGenerating}/>
              <span>Summarize text</span>
            </label>)}


          <div className="form-actions">

            <button type="submit" disabled={!canGenerate}>

              {jobStatus === 'cancel_requested'
            ? 'Cancelling'
            : isGenerating
                ? creationMode === 'podcast'
                    ? 'Producing podcast'
                    : 'Generating audio'
                : creationMode === 'podcast'
                    ? 'Approve & generate podcast'
                    : 'Generate Audio'}
            </button>

            {isGenerating && currentJobId ? (<button className="cancel-generation" type="button" disabled={cancellingJobId === currentJobId} onClick={() => handleCancelJob(currentJobId, true)}>
                {cancellingJobId === currentJobId ? 'Cancelling' : 'Cancel'}
              </button>) : null}
          </div>
        </form>


        {displayedGenerationStatus ? (<p className="generation-status" role="status">

            {displayedGenerationStatus}
          </p>) : null}


        {jobStatus === 'generating' ? (<progress className="generation-progress" aria-label="Audio generation progress" max={100} value={jobProgress}/>) : null}


        {error ? (<p className="error-message" role="alert">

            {error}
          </p>) : null}


        {resolvedAudioUrl ? (<section className="result-panel" aria-label="Generated result">

            <audio aria-label="Generated audio" controls src={resolvedAudioUrl}/>


            {summarizedText ? (<div className="summary-panel">

                <h2>Generated text</h2>

                <p>{summarizedText}</p>
              </div>) : null}
          </section>) : null}


        <section className="history-section" aria-labelledby="history-title">

          <div className="history-heading">

            <h2 id="history-title">Recent Generations</h2>

            <span>{audioJobs.length}</span>
          </div>


          {isLoadingHistory ? (<p className="history-state" role="status">
              Loading recent generations
            </p>) : null}


          {historyError ? (<p className="history-error" role="alert">
              {historyError}
            </p>) : null}


          {!isLoadingHistory && audioJobs.length === 0 ? (<p className="history-state">No generated audio yet.</p>) : (<div className="history-list">

              {audioJobs.map((job) => {
                const jobLanguage = languages.find((language) => language.code === job.language_code);
                const jobVoice = jobLanguage?.voices.find((voiceOption) => voiceOption.id === job.voice);
                const jobAudioUrl = job.audio_url
                    ? buildAudioUrl(job.audio_url)
                    : null;
                const jobStatusText = job.status === 'failed'
                    ? job.error ?? 'Generation failed'
                    : job.status === 'cancel_requested'
                        ? 'Cancelling'
                        : job.status === 'cancelled'
                            ? 'Cancelled'
                            : job.status === 'queued' && job.queue_position
                                ? `Queued · Position ${job.queue_position}`
                                : job.status === 'generating'
                                    ? `Generating · ${job.progress}%`
                                    : job.status;
                return (<article className="history-item" key={job.job_id}>

                    <div className="history-summary">

                      <h3>{job.text_preview}</h3>

                      <p>
                        {jobLanguage?.label ?? job.language_code}
                        {' · '}
                        {jobVoice?.label ?? job.voice}
                        {' · '}
                        {formatJobDate(job.created_at)}
                      </p>
                    </div>


                    {job.status !== 'done' ? (<p className={`history-status history-status-${job.status}`}>
                        {jobStatusText}
                      </p>) : null}


                    {job.status === 'generating' ? (<progress className="history-progress" aria-label={`Generation progress for ${job.text_preview}`} max={100} value={job.progress}/>) : null}


                    {jobAudioUrl ? (<audio aria-label={`Generated audio for ${job.text_preview}`} controls preload="none" src={jobAudioUrl}/>) : null}


                    {job.status === 'done'
                        || job.status === 'failed'
                        || job.status === 'cancelled'
                        || isActiveAudioJobStatus(job.status) ? (<div className="history-actions">

                        {job.status === 'done' ? (<a className="history-download" href={buildAudioJobDownloadUrl(job.job_id)}>
                            Download
                          </a>) : null}

                        {isActiveAudioJobStatus(job.status) ? (<button className="history-delete" type="button" disabled={cancellingJobId === job.job_id
                                || job.status === 'cancel_requested'} onClick={() => handleCancelJob(job.job_id)}>
                            {cancellingJobId === job.job_id
                                || job.status === 'cancel_requested'
                                ? 'Cancelling'
                                : 'Cancel'}
                          </button>) : (<button className="history-delete" type="button" disabled={deletingJobId === job.job_id} onClick={() => handleDeleteJob(job)}>
                            {deletingJobId === job.job_id ? 'Deleting' : 'Delete'}
                          </button>)}
                      </div>) : null}
                  </article>);
            })}
            </div>)}
        </section>
      </section>
    </main>);
}
