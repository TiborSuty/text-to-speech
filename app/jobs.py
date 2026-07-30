import os

import sqlite3

from dataclasses import dataclass

from datetime import UTC, datetime

from pathlib import Path

from threading import Lock

from uuid import uuid4


from app.audio_formats import AudioFormat
from app.models import AudioJobStatus


TERMINAL_JOB_STATUSES = {"cancelled", "done", "failed"}

TEXT_PREVIEW_LENGTH = 160

DATABASE_SCHEMA_VERSION = 4

DATABASE_PATH = Path(
    os.getenv(
        "AUDIO_JOBS_DB_PATH",
        Path(__file__).resolve().parent.parent / "data" / "audio_jobs.db",
    )
)

_database_initialization_lock = Lock()

_initialized_database_paths: set[Path] = set()


@dataclass(frozen=True)
class AudioJob:
    job_id: str

    status: AudioJobStatus

    language_code: str

    voice: str

    summarize: bool

    text_preview: str

    created_at: datetime

    updated_at: datetime

    audio_format: AudioFormat = "wav"

    object_key: str | None = None

    summarized_text: str | None = None

    error: str | None = None

    progress: int = 0

    @property
    def audio_url(self) -> str | None:

        if self.object_key is None:
            return None

        return f"/api/audio-files/{self.object_key}"


def build_text_preview(text: str) -> str:

    normalized_text = " ".join(text.split())

    if len(normalized_text) <= TEXT_PREVIEW_LENGTH:
        return normalized_text

    return f"{normalized_text[: TEXT_PREVIEW_LENGTH - 1].rstrip()}…"


def _open_database() -> sqlite3.Connection:

    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DATABASE_PATH, timeout=30)

    connection.row_factory = sqlite3.Row

    connection.execute("PRAGMA foreign_keys = ON")

    connection.execute("PRAGMA busy_timeout = 30000")

    return connection


def _create_audio_job_schema(connection: sqlite3.Connection) -> None:

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS audio_jobs (
            job_id TEXT PRIMARY KEY,
            status TEXT NOT NULL CHECK (
                status IN (
                    'queued',
                    'summarizing',
                    'generating',
                    'cancel_requested',
                    'cancelled',
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
            error TEXT,
            progress INTEGER NOT NULL DEFAULT 0 CHECK (
                progress BETWEEN 0 AND 100
            ),
            audio_format TEXT NOT NULL DEFAULT 'wav' CHECK (
                audio_format IN ('wav', 'mp3', 'flac', 'ogg')
            )
        )
        """
    )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS audio_jobs_created_at_idx
        ON audio_jobs(created_at DESC)
        """
    )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS audio_jobs_retention_idx
        ON audio_jobs(status, updated_at)
        """
    )


def _migrate_audio_job_schema_v1_to_v3(connection: sqlite3.Connection) -> None:

    connection.execute("BEGIN IMMEDIATE")

    connection.execute("ALTER TABLE audio_jobs RENAME TO audio_jobs_v1")

    connection.execute("DROP INDEX IF EXISTS audio_jobs_created_at_idx")
    connection.execute("DROP INDEX IF EXISTS audio_jobs_retention_idx")

    _create_audio_job_schema(connection)

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
            object_key,
            summarized_text,
            error
        )
        SELECT
            job_id,
            status,
            language_code,
            voice,
            summarize,
            text_preview,
            created_at,
            updated_at,
            object_key,
            summarized_text,
            error
        FROM audio_jobs_v1
        """
    )

    connection.execute("UPDATE audio_jobs SET progress = 100 WHERE status = 'done'")

    connection.execute("DROP TABLE audio_jobs_v1")


def _migrate_audio_job_schema_v2_to_v3(connection: sqlite3.Connection) -> None:

    connection.execute(
        """
        ALTER TABLE audio_jobs
        ADD COLUMN progress INTEGER NOT NULL DEFAULT 0
        CHECK (progress BETWEEN 0 AND 100)
        """
    )

    connection.execute("UPDATE audio_jobs SET progress = 100 WHERE status = 'done'")


def _migrate_audio_job_schema_v3_to_v4(connection: sqlite3.Connection) -> None:

    connection.execute(
        """
        ALTER TABLE audio_jobs
        ADD COLUMN audio_format TEXT NOT NULL DEFAULT 'wav'
        CHECK (audio_format IN ('wav', 'mp3', 'flac', 'ogg'))
        """
    )


def initialize_audio_job_store() -> None:

    database_path = DATABASE_PATH.resolve()

    if database_path in _initialized_database_paths:
        return

    with _database_initialization_lock:
        if database_path in _initialized_database_paths:
            return

        with _open_database() as connection:
            schema_version = connection.execute("PRAGMA user_version").fetchone()[0]

            if schema_version > DATABASE_SCHEMA_VERSION:
                raise RuntimeError(
                    "Audio job database schema is newer than this application"
                )

            if schema_version == 0:
                _create_audio_job_schema(connection)

            elif schema_version == 1:
                _migrate_audio_job_schema_v1_to_v3(connection)
                schema_version = 4

            elif schema_version == 2:
                _migrate_audio_job_schema_v2_to_v3(connection)
                schema_version = 3

            if schema_version == 3:
                _migrate_audio_job_schema_v3_to_v4(connection)

            connection.execute(f"PRAGMA user_version = {DATABASE_SCHEMA_VERSION}")

            connection.commit()

            connection.execute("PRAGMA journal_mode = WAL")

        _initialized_database_paths.add(database_path)


def _connect() -> sqlite3.Connection:

    initialize_audio_job_store()

    return _open_database()


def _row_to_audio_job(row: sqlite3.Row) -> AudioJob:

    return AudioJob(
        job_id=row["job_id"],
        status=row["status"],
        language_code=row["language_code"],
        voice=row["voice"],
        summarize=bool(row["summarize"]),
        text_preview=row["text_preview"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        audio_format=row["audio_format"],
        object_key=row["object_key"],
        summarized_text=row["summarized_text"],
        error=row["error"],
        progress=row["progress"],
    )


def create_audio_job_record(
    language_code: str,
    voice: str,
    text: str,
    summarize: bool,
    audio_format: AudioFormat = "wav",
    job_id: str | None = None,
) -> AudioJob:

    now = datetime.now(UTC)

    job = AudioJob(
        job_id=job_id or uuid4().hex,
        status="queued",
        language_code=language_code,
        voice=voice,
        summarize=summarize,
        text_preview=build_text_preview(text),
        created_at=now,
        updated_at=now,
        audio_format=audio_format,
    )

    with _connect() as connection:
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
                object_key,
                summarized_text,
                error,
                progress,
                audio_format
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.job_id,
                job.status,
                job.language_code,
                job.voice,
                int(job.summarize),
                job.text_preview,
                job.created_at.isoformat(),
                job.updated_at.isoformat(),
                job.object_key,
                job.summarized_text,
                job.error,
                job.progress,
                job.audio_format,
            ),
        )

    return job


def get_audio_job_record(job_id: str) -> AudioJob | None:

    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM audio_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()

    if row is None:
        return None

    return _row_to_audio_job(row)


def list_audio_job_records(limit: int) -> list[AudioJob]:

    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM audio_jobs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [_row_to_audio_job(row) for row in rows]


def list_completed_audio_job_records() -> list[AudioJob]:

    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM audio_jobs
            WHERE status = 'done' AND object_key IS NOT NULL
            """
        ).fetchall()

    return [_row_to_audio_job(row) for row in rows]


def update_audio_job_status(job_id: str, status: AudioJobStatus) -> bool:

    with _connect() as connection:
        cursor = connection.execute(
            """
            UPDATE audio_jobs
            SET status = ?, updated_at = ?, error = NULL
            WHERE job_id = ?
              AND status NOT IN ('cancel_requested', 'cancelled', 'done', 'failed')
            """,
            (status, datetime.now(UTC).isoformat(), job_id),
        )

        if cursor.rowcount > 0:
            return True

        existing_row = connection.execute(
            "SELECT 1 FROM audio_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()

        if existing_row is None:
            raise KeyError(job_id)

    return False


def update_audio_job_progress(job_id: str, progress: int) -> bool:

    if progress < 0 or progress > 99:
        raise ValueError("Active audio job progress must be between 0 and 99")

    with _connect() as connection:
        cursor = connection.execute(
            """
            UPDATE audio_jobs
            SET progress = ?, updated_at = ?
            WHERE job_id = ?
              AND status = 'generating'
              AND progress < ?
            """,
            (
                progress,
                datetime.now(UTC).isoformat(),
                job_id,
                progress,
            ),
        )

        if cursor.rowcount > 0:
            return True

        row = connection.execute(
            "SELECT status, progress FROM audio_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()

        if row is None:
            raise KeyError(job_id)

        if row["status"] == "generating":
            return True

    return False


def complete_audio_job_record(
    job_id: str,
    object_key: str,
    summarized_text: str | None,
) -> bool:

    with _connect() as connection:
        cursor = connection.execute(
            """
            UPDATE audio_jobs
            SET
                status = 'done',
                object_key = ?,
                summarized_text = ?,
                error = NULL,
                progress = 100,
                updated_at = ?
            WHERE job_id = ?
              AND status NOT IN ('cancel_requested', 'cancelled', 'done', 'failed')
            """,
            (
                object_key,
                summarized_text,
                datetime.now(UTC).isoformat(),
                job_id,
            ),
        )

        if cursor.rowcount > 0:
            return True

        existing_row = connection.execute(
            "SELECT 1 FROM audio_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()

        if existing_row is None:
            raise KeyError(job_id)

    return False


def fail_audio_job_record(job_id: str, error: str) -> bool:

    with _connect() as connection:
        cursor = connection.execute(
            """
            UPDATE audio_jobs
            SET
                status = 'failed',
                object_key = NULL,
                error = ?,
                updated_at = ?
            WHERE job_id = ?
              AND status NOT IN ('cancel_requested', 'cancelled', 'done')
            """,
            (error, datetime.now(UTC).isoformat(), job_id),
        )

        if cursor.rowcount > 0:
            return True

        existing_row = connection.execute(
            "SELECT 1 FROM audio_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()

        if existing_row is None:
            raise KeyError(job_id)

    return False


def mark_audio_job_output_missing(job_id: str) -> bool:

    with _connect() as connection:
        cursor = connection.execute(
            """
            UPDATE audio_jobs
            SET
                status = 'failed',
                object_key = NULL,
                error = 'Stored audio is no longer available',
                updated_at = ?
            WHERE job_id = ? AND status = 'done'
            """,
            (datetime.now(UTC).isoformat(), job_id),
        )

    return cursor.rowcount > 0


def request_audio_job_cancellation(job_id: str) -> AudioJob | None:

    with _connect() as connection:
        connection.execute("BEGIN IMMEDIATE")

        row = connection.execute(
            "SELECT * FROM audio_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()

        if row is None:
            return None

        next_status = "cancelled" if row["status"] == "queued" else "cancel_requested"

        if row["status"] in TERMINAL_JOB_STATUSES:
            return _row_to_audio_job(row)

        if row["status"] == "cancel_requested":
            return _row_to_audio_job(row)

        connection.execute(
            """
            UPDATE audio_jobs
            SET
                status = ?,
                object_key = NULL,
                error = NULL,
                updated_at = ?
            WHERE job_id = ?
            """,
            (next_status, datetime.now(UTC).isoformat(), job_id),
        )

        updated_row = connection.execute(
            "SELECT * FROM audio_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()

    return _row_to_audio_job(updated_row)


def finalize_audio_job_cancellation(job_id: str) -> bool:

    with _connect() as connection:
        cursor = connection.execute(
            """
            UPDATE audio_jobs
            SET
                status = 'cancelled',
                object_key = NULL,
                error = NULL,
                updated_at = ?
            WHERE job_id = ? AND status = 'cancel_requested'
            """,
            (datetime.now(UTC).isoformat(), job_id),
        )

    return cursor.rowcount > 0


def delete_audio_job_record(job_id: str) -> AudioJob | None:

    with _connect() as connection:
        connection.execute("BEGIN IMMEDIATE")

        row = connection.execute(
            "SELECT * FROM audio_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()

        if row is None:
            return None

        connection.execute(
            "DELETE FROM audio_jobs WHERE job_id = ?",
            (job_id,),
        )

    return _row_to_audio_job(row)


def remove_expired_audio_job_records(cutoff: datetime) -> list[AudioJob]:

    with _connect() as connection:
        connection.execute("BEGIN IMMEDIATE")

        rows = connection.execute(
            """
            SELECT *
            FROM audio_jobs
            WHERE status IN ('cancelled', 'done', 'failed') AND updated_at < ?
            """,
            (cutoff.isoformat(),),
        ).fetchall()

        expired_job_ids = [row["job_id"] for row in rows]

        connection.executemany(
            "DELETE FROM audio_jobs WHERE job_id = ?",
            ((job_id,) for job_id in expired_job_ids),
        )

    return [_row_to_audio_job(row) for row in rows]


def recover_interrupted_audio_jobs() -> int:

    with _connect() as connection:
        cancelled_cursor = connection.execute(
            """
            UPDATE audio_jobs
            SET
                status = 'cancelled',
                object_key = NULL,
                error = NULL,
                updated_at = ?
            WHERE status = 'cancel_requested'
            """,
            (datetime.now(UTC).isoformat(),),
        )

        failed_cursor = connection.execute(
            """
            UPDATE audio_jobs
            SET
                status = 'failed',
                object_key = NULL,
                error = 'Generation was interrupted by a backend restart',
                updated_at = ?
            WHERE status IN ('queued', 'summarizing', 'generating')
            """,
            (datetime.now(UTC).isoformat(),),
        )

    return cancelled_cursor.rowcount + failed_cursor.rowcount


def clear_audio_job_records() -> None:

    with _connect() as connection:
        connection.execute("DELETE FROM audio_jobs")
