import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import cast
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    delete,
    event,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Connection, Engine, RowMapping
from sqlalchemy.pool import NullPool

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

_database_engines: dict[Path, Engine] = {}

_metadata = MetaData()

_audio_jobs = Table(
    "audio_jobs",
    _metadata,
    Column("job_id", String, primary_key=True),
    Column("status", String, nullable=False),
    Column("language_code", String, nullable=False),
    Column("voice", String, nullable=False),
    Column("summarize", Integer, nullable=False),
    Column("text_preview", String, nullable=False),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
    Column("object_key", String),
    Column("summarized_text", String),
    Column("error", String),
    Column("progress", Integer, nullable=False, server_default="0"),
    Column("audio_format", String, nullable=False, server_default="wav"),
    CheckConstraint(
        "status IN ("
        "'queued', 'summarizing', 'generating', 'cancel_requested', "
        "'cancelled', 'done', 'failed'"
        ")",
        name="audio_jobs_status_check",
    ),
    CheckConstraint("summarize IN (0, 1)", name="audio_jobs_summarize_check"),
    CheckConstraint(
        "progress BETWEEN 0 AND 100",
        name="audio_jobs_progress_check",
    ),
    CheckConstraint(
        "audio_format IN ('wav', 'mp3', 'flac', 'ogg')",
        name="audio_jobs_audio_format_check",
    ),
)

_created_at_index = Index(
    "audio_jobs_created_at_idx",
    _audio_jobs.c.created_at.desc(),
)

_retention_index = Index(
    "audio_jobs_retention_idx",
    _audio_jobs.c.status,
    _audio_jobs.c.updated_at,
)


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


def _get_database_engine() -> Engine:
    database_path = DATABASE_PATH.resolve()
    engine = _database_engines.get(database_path)

    if engine is not None:
        return engine

    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite+pysqlite:///{database_path}",
        connect_args={"timeout": 30},
        poolclass=NullPool,
    )

    @event.listens_for(engine, "connect")
    def configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA busy_timeout = 30000")
        cursor.close()

    _database_engines[database_path] = engine
    return engine


def _open_database() -> Connection:
    return _get_database_engine().connect()


def _create_audio_job_schema(connection: Connection) -> None:
    _metadata.create_all(connection)


def _migrate_audio_job_schema_v1_to_v3(connection: Connection) -> None:
    connection.exec_driver_sql("BEGIN IMMEDIATE")
    connection.exec_driver_sql("ALTER TABLE audio_jobs RENAME TO audio_jobs_v1")

    _created_at_index.drop(connection, checkfirst=True)
    _retention_index.drop(connection, checkfirst=True)
    _create_audio_job_schema(connection)

    legacy_audio_jobs = Table(
        "audio_jobs_v1",
        MetaData(),
        autoload_with=connection,
    )
    migrated_column_names = [
        "job_id",
        "status",
        "language_code",
        "voice",
        "summarize",
        "text_preview",
        "created_at",
        "updated_at",
        "object_key",
        "summarized_text",
        "error",
    ]
    connection.execute(
        insert(_audio_jobs).from_select(
            migrated_column_names,
            select(*(legacy_audio_jobs.c[name] for name in migrated_column_names)),
        )
    )
    connection.execute(
        update(_audio_jobs).where(_audio_jobs.c.status == "done").values(progress=100)
    )
    legacy_audio_jobs.drop(connection)


def _migrate_audio_job_schema_v2_to_v3(connection: Connection) -> None:
    connection.exec_driver_sql(
        """
        ALTER TABLE audio_jobs
        ADD COLUMN progress INTEGER NOT NULL DEFAULT 0
        CHECK (progress BETWEEN 0 AND 100)
        """
    )
    connection.execute(
        update(_audio_jobs).where(_audio_jobs.c.status == "done").values(progress=100)
    )


def _migrate_audio_job_schema_v3_to_v4(connection: Connection) -> None:
    connection.exec_driver_sql(
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
            schema_version = connection.exec_driver_sql(
                "PRAGMA user_version"
            ).scalar_one()
            connection.commit()

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

            connection.exec_driver_sql(
                f"PRAGMA user_version = {DATABASE_SCHEMA_VERSION}"
            )

            connection.commit()

            connection.exec_driver_sql("PRAGMA journal_mode = WAL")
            connection.commit()

        _initialized_database_paths.add(database_path)


@contextmanager
def _connect(*, immediate: bool = False) -> Iterator[Connection]:
    initialize_audio_job_store()

    connection = _open_database()
    try:
        if immediate:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        else:
            connection.begin()

        yield connection
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()
    finally:
        connection.close()


def _row_to_audio_job(row: RowMapping) -> AudioJob:
    return AudioJob(
        job_id=row["job_id"],
        status=cast(AudioJobStatus, row["status"]),
        language_code=row["language_code"],
        voice=row["voice"],
        summarize=bool(row["summarize"]),
        text_preview=row["text_preview"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        audio_format=cast(AudioFormat, row["audio_format"]),
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
            insert(_audio_jobs).values(
                job_id=job.job_id,
                status=job.status,
                language_code=job.language_code,
                voice=job.voice,
                summarize=int(job.summarize),
                text_preview=job.text_preview,
                created_at=job.created_at.isoformat(),
                updated_at=job.updated_at.isoformat(),
                object_key=job.object_key,
                summarized_text=job.summarized_text,
                error=job.error,
                progress=job.progress,
                audio_format=job.audio_format,
            )
        )

    return job


def get_audio_job_record(job_id: str) -> AudioJob | None:

    with _connect() as connection:
        row = (
            connection.execute(
                select(_audio_jobs).where(_audio_jobs.c.job_id == job_id)
            )
            .mappings()
            .one_or_none()
        )

    if row is None:
        return None

    return _row_to_audio_job(row)


def list_audio_job_records(limit: int) -> list[AudioJob]:

    with _connect() as connection:
        rows = (
            connection.execute(
                select(_audio_jobs)
                .order_by(_audio_jobs.c.created_at.desc())
                .limit(limit)
            )
            .mappings()
            .all()
        )

    return [_row_to_audio_job(row) for row in rows]


def list_completed_audio_job_records() -> list[AudioJob]:

    with _connect() as connection:
        rows = (
            connection.execute(
                select(_audio_jobs).where(
                    _audio_jobs.c.status == "done",
                    _audio_jobs.c.object_key.is_not(None),
                )
            )
            .mappings()
            .all()
        )

    return [_row_to_audio_job(row) for row in rows]


def update_audio_job_status(job_id: str, status: AudioJobStatus) -> bool:

    with _connect() as connection:
        result = connection.execute(
            update(_audio_jobs)
            .where(
                _audio_jobs.c.job_id == job_id,
                _audio_jobs.c.status.not_in(
                    ("cancel_requested", "cancelled", "done", "failed")
                ),
            )
            .values(
                status=status,
                updated_at=datetime.now(UTC).isoformat(),
                error=None,
            )
        )

        if result.rowcount > 0:
            return True

        existing_row = connection.execute(
            select(_audio_jobs.c.job_id).where(_audio_jobs.c.job_id == job_id)
        ).one_or_none()

        if existing_row is None:
            raise KeyError(job_id)

    return False


def update_audio_job_progress(job_id: str, progress: int) -> bool:

    if progress < 0 or progress > 99:
        raise ValueError("Active audio job progress must be between 0 and 99")

    with _connect() as connection:
        result = connection.execute(
            update(_audio_jobs)
            .where(
                _audio_jobs.c.job_id == job_id,
                _audio_jobs.c.status == "generating",
                _audio_jobs.c.progress < progress,
            )
            .values(
                progress=progress,
                updated_at=datetime.now(UTC).isoformat(),
            )
        )

        if result.rowcount > 0:
            return True

        row = (
            connection.execute(
                select(_audio_jobs.c.status, _audio_jobs.c.progress).where(
                    _audio_jobs.c.job_id == job_id
                )
            )
            .mappings()
            .one_or_none()
        )

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
        result = connection.execute(
            update(_audio_jobs)
            .where(
                _audio_jobs.c.job_id == job_id,
                _audio_jobs.c.status.not_in(
                    ("cancel_requested", "cancelled", "done", "failed")
                ),
            )
            .values(
                status="done",
                object_key=object_key,
                summarized_text=summarized_text,
                error=None,
                progress=100,
                updated_at=datetime.now(UTC).isoformat(),
            )
        )

        if result.rowcount > 0:
            return True

        existing_row = connection.execute(
            select(_audio_jobs.c.job_id).where(_audio_jobs.c.job_id == job_id)
        ).one_or_none()

        if existing_row is None:
            raise KeyError(job_id)

    return False


def fail_audio_job_record(job_id: str, error: str) -> bool:

    with _connect() as connection:
        result = connection.execute(
            update(_audio_jobs)
            .where(
                _audio_jobs.c.job_id == job_id,
                _audio_jobs.c.status.not_in(("cancel_requested", "cancelled", "done")),
            )
            .values(
                status="failed",
                object_key=None,
                error=error,
                updated_at=datetime.now(UTC).isoformat(),
            )
        )

        if result.rowcount > 0:
            return True

        existing_row = connection.execute(
            select(_audio_jobs.c.job_id).where(_audio_jobs.c.job_id == job_id)
        ).one_or_none()

        if existing_row is None:
            raise KeyError(job_id)

    return False


def mark_audio_job_output_missing(job_id: str) -> bool:

    with _connect() as connection:
        result = connection.execute(
            update(_audio_jobs)
            .where(
                _audio_jobs.c.job_id == job_id,
                _audio_jobs.c.status == "done",
            )
            .values(
                status="failed",
                object_key=None,
                error="Stored audio is no longer available",
                updated_at=datetime.now(UTC).isoformat(),
            )
        )

    return result.rowcount > 0


def request_audio_job_cancellation(job_id: str) -> AudioJob | None:

    with _connect(immediate=True) as connection:
        row = (
            connection.execute(
                select(_audio_jobs).where(_audio_jobs.c.job_id == job_id)
            )
            .mappings()
            .one_or_none()
        )

        if row is None:
            return None

        next_status = "cancelled" if row["status"] == "queued" else "cancel_requested"

        if row["status"] in TERMINAL_JOB_STATUSES:
            return _row_to_audio_job(row)

        if row["status"] == "cancel_requested":
            return _row_to_audio_job(row)

        connection.execute(
            update(_audio_jobs)
            .where(_audio_jobs.c.job_id == job_id)
            .values(
                status=next_status,
                object_key=None,
                error=None,
                updated_at=datetime.now(UTC).isoformat(),
            )
        )

        updated_row = (
            connection.execute(
                select(_audio_jobs).where(_audio_jobs.c.job_id == job_id)
            )
            .mappings()
            .one()
        )

    return _row_to_audio_job(updated_row)


def finalize_audio_job_cancellation(job_id: str) -> bool:

    with _connect() as connection:
        result = connection.execute(
            update(_audio_jobs)
            .where(
                _audio_jobs.c.job_id == job_id,
                _audio_jobs.c.status == "cancel_requested",
            )
            .values(
                status="cancelled",
                object_key=None,
                error=None,
                updated_at=datetime.now(UTC).isoformat(),
            )
        )

    return result.rowcount > 0


def delete_audio_job_record(job_id: str) -> AudioJob | None:

    with _connect(immediate=True) as connection:
        row = (
            connection.execute(
                select(_audio_jobs).where(_audio_jobs.c.job_id == job_id)
            )
            .mappings()
            .one_or_none()
        )

        if row is None:
            return None

        connection.execute(delete(_audio_jobs).where(_audio_jobs.c.job_id == job_id))

    return _row_to_audio_job(row)


def remove_expired_audio_job_records(cutoff: datetime) -> list[AudioJob]:

    with _connect(immediate=True) as connection:
        rows = (
            connection.execute(
                select(_audio_jobs).where(
                    _audio_jobs.c.status.in_(TERMINAL_JOB_STATUSES),
                    _audio_jobs.c.updated_at < cutoff.isoformat(),
                )
            )
            .mappings()
            .all()
        )

        expired_job_ids = [row["job_id"] for row in rows]

        if expired_job_ids:
            connection.execute(
                delete(_audio_jobs).where(_audio_jobs.c.job_id.in_(expired_job_ids))
            )

    return [_row_to_audio_job(row) for row in rows]


def recover_interrupted_audio_jobs() -> int:

    with _connect() as connection:
        cancelled_result = connection.execute(
            update(_audio_jobs)
            .where(_audio_jobs.c.status == "cancel_requested")
            .values(
                status="cancelled",
                object_key=None,
                error=None,
                updated_at=datetime.now(UTC).isoformat(),
            )
        )

        failed_result = connection.execute(
            update(_audio_jobs)
            .where(_audio_jobs.c.status.in_(("queued", "summarizing", "generating")))
            .values(
                status="failed",
                object_key=None,
                error="Generation was interrupted by a backend restart",
                updated_at=datetime.now(UTC).isoformat(),
            )
        )

    return cancelled_result.rowcount + failed_result.rowcount


def clear_audio_job_records() -> None:

    with _connect() as connection:
        connection.execute(delete(_audio_jobs))
