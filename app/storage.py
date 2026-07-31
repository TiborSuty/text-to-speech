import os
import shutil
from datetime import timedelta
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from minio import Minio
from minio.error import S3Error

from app.audio import AUDIO_DIR
from app.audio_formats import (
    get_audio_format_from_file_name,
    get_audio_format_spec,
)

DEFAULT_AUDIO_BUCKET = "audio"

PRESIGNED_URL_EXPIRY = timedelta(minutes=15)


class AudioObjectStorage(Protocol):
    def initialize(self) -> None: ...

    def put_file(self, source_path: Path, object_key: str) -> None: ...

    def exists(self, object_key: str) -> bool: ...

    def delete(self, object_key: str) -> None: ...

    def local_path(self, object_key: str) -> Path | None: ...

    def presigned_get_url(
        self,
        object_key: str,
        download_filename: str | None = None,
    ) -> str | None: ...


def validate_audio_object_key(object_key: str) -> str:

    if Path(object_key).name != object_key:
        raise ValueError("Audio object key must be a plain file name")

    audio_format = get_audio_format_from_file_name(object_key)

    if not object_key.removesuffix(f".{audio_format}").isalnum():
        raise ValueError("Audio object key must use an alphanumeric identifier")

    return object_key


class FilesystemAudioStorage:
    def __init__(self, directory: Path = AUDIO_DIR):

        self.directory = directory

    def initialize(self) -> None:

        self.directory.mkdir(parents=True, exist_ok=True)

    def put_file(self, source_path: Path, object_key: str) -> None:

        key = validate_audio_object_key(object_key)

        self.initialize()

        destination = self.directory / key

        if source_path.resolve() == destination.resolve():
            if not source_path.is_file():
                raise FileNotFoundError(source_path)

            return

        shutil.copy2(source_path, destination)

    def exists(self, object_key: str) -> bool:

        return (self.directory / validate_audio_object_key(object_key)).is_file()

    def delete(self, object_key: str) -> None:

        (self.directory / validate_audio_object_key(object_key)).unlink(missing_ok=True)

    def local_path(self, object_key: str) -> Path:

        return self.directory / validate_audio_object_key(object_key)

    def presigned_get_url(
        self,
        object_key: str,
        download_filename: str | None = None,
    ) -> None:

        validate_audio_object_key(object_key)

        return None


class MinioAudioStorage:
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool,
        public_endpoint: str | None,
        region: str,
    ):

        self.bucket = bucket

        self.client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
            region=region,
        )

        self.public_client = self._build_public_client(
            public_endpoint,
            access_key,
            secret_key,
            region,
        )

    def _build_public_client(
        self,
        public_endpoint: str | None,
        access_key: str,
        secret_key: str,
        region: str,
    ) -> Minio:

        if not public_endpoint:
            return self.client

        normalized_endpoint = (
            public_endpoint if "://" in public_endpoint else f"http://{public_endpoint}"
        )

        parsed_endpoint = urlsplit(normalized_endpoint)

        if not parsed_endpoint.hostname:
            raise ValueError("MINIO_PUBLIC_ENDPOINT must contain a host")

        public_host = parsed_endpoint.hostname
        if parsed_endpoint.port is not None:
            public_host = f"{public_host}:{parsed_endpoint.port}"

        return Minio(
            public_host,
            access_key=access_key,
            secret_key=secret_key,
            secure=parsed_endpoint.scheme == "https",
            region=region,
        )

    def initialize(self) -> None:

        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def put_file(self, source_path: Path, object_key: str) -> None:

        key = validate_audio_object_key(object_key)
        audio_format = get_audio_format_from_file_name(key)

        self.initialize()

        self.client.fput_object(
            self.bucket,
            key,
            str(source_path),
            content_type=get_audio_format_spec(audio_format).media_type,
        )

    def exists(self, object_key: str) -> bool:

        key = validate_audio_object_key(object_key)

        try:
            self.client.stat_object(self.bucket, key)

        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
                return False

            raise

        return True

    def delete(self, object_key: str) -> None:

        self.client.remove_object(
            self.bucket,
            validate_audio_object_key(object_key),
        )

    def local_path(self, object_key: str) -> None:

        validate_audio_object_key(object_key)

        return None

    def presigned_get_url(
        self,
        object_key: str,
        download_filename: str | None = None,
    ) -> str:

        key = validate_audio_object_key(object_key)
        audio_format = get_audio_format_from_file_name(key)

        response_headers = {
            "response-content-type": get_audio_format_spec(audio_format).media_type
        }

        if download_filename is not None:
            response_headers["response-content-disposition"] = (
                f'attachment; filename="{download_filename}"'
            )

        return self.public_client.presigned_get_object(
            self.bucket,
            key,
            expires=PRESIGNED_URL_EXPIRY,
            response_headers=response_headers,
        )


def create_audio_object_storage() -> AudioObjectStorage:

    backend = os.getenv("AUDIO_STORAGE_BACKEND", "filesystem").strip().lower()

    if backend == "filesystem":
        return FilesystemAudioStorage()

    if backend != "minio":
        raise ValueError("AUDIO_STORAGE_BACKEND must be 'filesystem' or 'minio'")

    return MinioAudioStorage(
        endpoint=os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000"),
        access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
        secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
        bucket=os.getenv("MINIO_BUCKET", DEFAULT_AUDIO_BUCKET),
        secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
        public_endpoint=os.getenv("MINIO_PUBLIC_ENDPOINT"),
        region=os.getenv("MINIO_REGION", "us-east-1"),
    )
