from datetime import UTC, datetime, timedelta


from app.jobs import (
    DATABASE_SCHEMA_VERSION,
    complete_audio_job_record,
    create_audio_job_record,
    delete_audio_job_record,
    get_audio_job_record,
    initialize_audio_job_store,
    recover_interrupted_audio_jobs,
    remove_expired_audio_job_records,
    request_audio_job_cancellation,
    update_audio_job_progress,
    update_audio_job_status,
)


def test_retention_removes_only_terminal_jobs():

    active_job = create_audio_job_record(
        language_code="a",
        voice="af_heart",
        text="Active job",
        summarize=False,
    )

    completed_job = create_audio_job_record(
        language_code="b",
        voice="bf_emma",
        text="Completed job",
        summarize=False,
    )

    complete_audio_job_record(
        completed_job.job_id,
        f"{completed_job.job_id}.wav",
        None,
    )

    cutoff = datetime.now(UTC) + timedelta(seconds=1)

    removed_jobs = remove_expired_audio_job_records(cutoff)

    removed_job_ids = {job.job_id for job in removed_jobs}

    assert completed_job.job_id in removed_job_ids

    assert active_job.job_id not in removed_job_ids

    delete_audio_job_record(active_job.job_id)


def test_job_metadata_persists_across_repository_reinitialization(
    monkeypatch, tmp_path
):

    import sqlite3

    from app import jobs

    database_path = tmp_path / "persistent" / "audio_jobs.db"

    monkeypatch.setattr(jobs, "DATABASE_PATH", database_path)

    initialize_audio_job_store()
    created_job = create_audio_job_record(
        language_code="a",
        voice="af_heart",
        text="Persistent episode",
        summarize=True,
    )
    complete_audio_job_record(
        created_job.job_id,
        f"{created_job.job_id}.wav",
        "Persistent summary",
    )

    jobs._initialized_database_paths.discard(database_path.resolve())

    initialize_audio_job_store()
    persisted_job = get_audio_job_record(created_job.job_id)

    assert persisted_job is not None
    assert persisted_job.status == "done"
    assert persisted_job.object_key == f"{created_job.job_id}.wav"
    assert persisted_job.audio_url == f"/api/audio-files/{created_job.job_id}.wav"
    assert persisted_job.summarized_text == "Persistent summary"
    assert persisted_job.progress == 100

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == (
            DATABASE_SCHEMA_VERSION
        )


def test_restart_recovery_marks_active_jobs_failed():

    active_job = create_audio_job_record(
        language_code="a",
        voice="af_heart",
        text="Interrupted episode",
        summarize=False,
    )

    recovered_count = recover_interrupted_audio_jobs()
    recovered_job = get_audio_job_record(active_job.job_id)

    assert recovered_count == 1
    assert recovered_job is not None
    assert recovered_job.status == "failed"
    assert recovered_job.error == "Generation was interrupted by a backend restart"


def test_restart_recovery_completes_requested_cancellation():

    active_job = create_audio_job_record(
        language_code="a",
        voice="af_heart",
        text="Cancel before restart",
        summarize=False,
    )
    assert update_audio_job_status(active_job.job_id, "generating") is True
    requested_job = request_audio_job_cancellation(active_job.job_id)
    assert requested_job is not None
    assert requested_job.status == "cancel_requested"

    recovered_count = recover_interrupted_audio_jobs()
    recovered_job = get_audio_job_record(active_job.job_id)

    assert recovered_count == 1
    assert recovered_job is not None
    assert recovered_job.status == "cancelled"
    assert recovered_job.error is None


def test_queued_cancellation_is_terminal_and_idempotent():

    queued_job = create_audio_job_record(
        language_code="a",
        voice="af_heart",
        text="Cancel in queue",
        summarize=False,
    )

    first_result = request_audio_job_cancellation(queued_job.job_id)
    second_result = request_audio_job_cancellation(queued_job.job_id)

    assert first_result is not None
    assert first_result.status == "cancelled"
    assert second_result is not None
    assert second_result.status == "cancelled"


def test_generation_progress_is_durable_and_cancellation_aware():

    active_job = create_audio_job_record(
        language_code="a",
        voice="af_heart",
        text="Track progress",
        summarize=False,
    )
    assert update_audio_job_status(active_job.job_id, "generating") is True

    assert update_audio_job_progress(active_job.job_id, 25) is True
    assert update_audio_job_progress(active_job.job_id, 70) is True
    assert update_audio_job_progress(active_job.job_id, 40) is True
    progressed_job = get_audio_job_record(active_job.job_id)

    assert progressed_job is not None
    assert progressed_job.progress == 70

    requested_job = request_audio_job_cancellation(active_job.job_id)
    assert requested_job is not None
    assert requested_job.status == "cancel_requested"
    assert update_audio_job_progress(active_job.job_id, 80) is False


def test_storage_reconciliation_marks_missing_audio_failed():

    from app.main import reconcile_audio_job_storage

    completed_job = create_audio_job_record(
        language_code="a",
        voice="af_heart",
        text="Missing recording",
        summarize=False,
    )
    complete_audio_job_record(
        completed_job.job_id,
        f"{completed_job.job_id}.wav",
        None,
    )

    class MissingObjectStorage:
        def exists(self, object_key: str) -> bool:
            assert object_key == f"{completed_job.job_id}.wav"
            return False

    reconcile_audio_job_storage(MissingObjectStorage())
    reconciled_job = get_audio_job_record(completed_job.job_id)

    assert reconciled_job is not None
    assert reconciled_job.status == "failed"
    assert reconciled_job.object_key is None
    assert reconciled_job.audio_url is None
    assert reconciled_job.error == "Stored audio is no longer available"


def test_version_one_database_migrates_to_cancellation_schema(monkeypatch, tmp_path):

    import sqlite3

    from app import jobs

    database_path = tmp_path / "legacy" / "audio_jobs.db"
    database_path.parent.mkdir()
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE audio_jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT NOT NULL CHECK (
                    status IN (
                        'queued',
                        'summarizing',
                        'generating',
                        'done',
                        'failed'
                    )
                ),
                language_code TEXT NOT NULL,
                voice TEXT NOT NULL,
                summarize INTEGER NOT NULL CHECK (summarize IN (0, 1)),
                text_preview TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                object_key TEXT,
                summarized_text TEXT,
                error TEXT
            );
            PRAGMA user_version = 1;
            """
        )

        timestamp = datetime.now(UTC).isoformat()
        connection.execute(
            """
            INSERT INTO audio_jobs (
                job_id,
                status,
                language_code,
                voice,
                summarize,
                text_preview,
                created_at,
                updated_at
            ) VALUES (?, 'queued', 'a', 'af_heart', 0, ?, ?, ?)
            """,
            ("legacyjob", "Legacy job", timestamp, timestamp),
        )

    monkeypatch.setattr(jobs, "DATABASE_PATH", database_path)
    jobs._initialized_database_paths.discard(database_path.resolve())
    initialize_audio_job_store()

    migrated_job = request_audio_job_cancellation("legacyjob")

    assert migrated_job is not None
    assert migrated_job.status == "cancelled"
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == (
            DATABASE_SCHEMA_VERSION
        )
        progress = connection.execute(
            "SELECT progress FROM audio_jobs WHERE job_id = 'legacyjob'"
        ).fetchone()[0]
        assert progress == 0


def test_version_two_database_migrates_to_progress_schema(monkeypatch, tmp_path):

    import sqlite3

    from app import jobs

    database_path = tmp_path / "version-two" / "audio_jobs.db"
    database_path.parent.mkdir()
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE audio_jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                language_code TEXT NOT NULL,
                voice TEXT NOT NULL,
                summarize INTEGER NOT NULL,
                text_preview TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                object_key TEXT,
                summarized_text TEXT,
                error TEXT
            );
            PRAGMA user_version = 2;
            """
        )

        timestamp = datetime.now(UTC).isoformat()
        connection.execute(
            """
            INSERT INTO audio_jobs (
                job_id,
                status,
                language_code,
                voice,
                summarize,
                text_preview,
                created_at,
                updated_at,
                object_key
            ) VALUES (?, 'done', 'a', 'af_heart', 0, ?, ?, ?, ?)
            """,
            (
                "versiontwojob",
                "Version two job",
                timestamp,
                timestamp,
                "versiontwojob.wav",
            ),
        )

    monkeypatch.setattr(jobs, "DATABASE_PATH", database_path)
    jobs._initialized_database_paths.discard(database_path.resolve())
    initialize_audio_job_store()
    migrated_job = get_audio_job_record("versiontwojob")

    assert migrated_job is not None
    assert migrated_job.status == "done"
    assert migrated_job.progress == 100
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == (
            DATABASE_SCHEMA_VERSION
        )
