import os
import tempfile
from pathlib import Path

os.environ["AUDIO_JOBS_DB_PATH"] = str(
    Path(tempfile.mkdtemp(prefix="text-to-speech-tests-")) / "audio_jobs.db"
)

os.environ["PODCAST_WORKFLOW_DB_PATH"] = str(
    Path(tempfile.mkdtemp(prefix="text-to-speech-workflow-tests-"))
    / "podcast_workflows.db"
)

os.environ["AUDIO_STORAGE_BACKEND"] = "filesystem"


import pytest


@pytest.fixture(autouse=True)
def isolate_persistent_storage(monkeypatch, tmp_path):

    from app import jobs, main
    from app.storage import FilesystemAudioStorage

    main.audio_worker_pool.shutdown()

    database_path = tmp_path / "data" / "audio_jobs.db"

    monkeypatch.setattr(jobs, "DATABASE_PATH", database_path)

    object_storage = FilesystemAudioStorage(tmp_path / "objects")

    monkeypatch.setattr(main, "audio_storage", object_storage)

    jobs.initialize_audio_job_store()

    yield

    main.audio_worker_pool.shutdown()
