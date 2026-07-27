# Imports dataclass helpers for compact job state objects.
from dataclasses import dataclass, replace
# Imports Lock so shared in-memory job state is safe across background threads.
from threading import Lock
# Imports uuid4 to create unique job IDs.
from uuid import uuid4

# Imports the restricted job status type used by API response models.
from app.models import AudioJobStatus

# Defines the statuses that mean a job will receive no more updates.
TERMINAL_JOB_STATUSES = {"done", "failed"}


# Stores mutable state for one asynchronous audio-generation job.
@dataclass
class AudioJob:
    # Stores the unique ID for this job.
    job_id: str
    # Stores the current lifecycle status.
    status: AudioJobStatus
    # Stores the generated audio URL after successful completion.
    audio_url: str | None = None
    # Stores the generated summary after successful completion.
    summarized_text: str | None = None
    # Stores a user-visible failure message after unsuccessful completion.
    error: str | None = None


# Holds all jobs created since the backend process started.
_jobs: dict[str, AudioJob] = {}
# Protects the shared jobs dictionary and each job's mutable fields.
_jobs_lock = Lock()


# Creates a new queued audio job and stores it in memory.
def create_audio_job_record() -> AudioJob:
    # Builds a job with a random hex ID and queued status.
    job = AudioJob(job_id=uuid4().hex, status="queued")
    # Locks the shared dictionary before writing the new job.
    with _jobs_lock:
        # Stores the job by ID so later endpoints can find it.
        _jobs[job.job_id] = job
    # Returns a copy so callers cannot mutate shared state without the lock.
    return replace(job)


# Reads one job from memory by ID.
def get_audio_job_record(job_id: str) -> AudioJob | None:
    # Locks the shared dictionary while reading the job.
    with _jobs_lock:
        # Looks up the job in the in-memory store.
        job = _jobs.get(job_id)
        # Returns None when the job ID is unknown.
        if job is None:
            # Signals that no matching job exists.
            return None
        # Returns a copy so callers observe a stable snapshot.
        return replace(job)


# Updates a job status and clears stale terminal fields when needed.
def update_audio_job_status(job_id: str, status: AudioJobStatus) -> None:
    # Locks shared state before mutating the job.
    with _jobs_lock:
        # Looks up the job to update.
        job = _jobs[job_id]
        # Stores the new lifecycle status.
        job.status = status
        # Clears the error while the job is still progressing.
        job.error = None


# Marks a job as successfully completed.
def complete_audio_job_record(
    job_id: str,
    audio_url: str,
    summarized_text: str | None,
) -> None:
    # Locks shared state before mutating the job.
    with _jobs_lock:
        # Looks up the job to complete.
        job = _jobs[job_id]
        # Marks the job as done.
        job.status = "done"
        # Stores the URL where the frontend can play the generated audio.
        job.audio_url = audio_url
        # Stores optional summary text produced during generation.
        job.summarized_text = summarized_text
        # Clears any prior error value.
        job.error = None


# Marks a job as failed.
def fail_audio_job_record(job_id: str, error: str) -> None:
    # Locks shared state before mutating the job.
    with _jobs_lock:
        # Looks up the job to fail.
        job = _jobs[job_id]
        # Marks the job as failed.
        job.status = "failed"
        # Stores the message the frontend should show to the user.
        job.error = error
