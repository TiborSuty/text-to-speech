from app.storage import (
    FilesystemAudioStorage,
    MinioAudioStorage,
    validate_audio_object_key,
)


def test_filesystem_audio_storage_lifecycle(tmp_path):

    source_path = tmp_path / "staging" / "job123.wav"
    source_path.parent.mkdir()
    source_path.write_bytes(b"wave-data")
    storage = FilesystemAudioStorage(tmp_path / "objects")

    storage.put_file(source_path, "job123.wav")
    stored_path = storage.local_path("job123.wav")

    assert stored_path.read_bytes() == b"wave-data"
    assert storage.exists("job123.wav") is True
    assert storage.presigned_get_url("job123.wav") is None

    storage.delete("job123.wav")
    storage.delete("job123.wav")
    assert storage.exists("job123.wav") is False


def test_minio_audio_storage_upload_and_presigned_download(monkeypatch, tmp_path):

    created_clients = []

    class FakeMinioClient:
        def __init__(
            self,
            endpoint: str,
            access_key: str,
            secret_key: str,
            secure: bool,
            region: str,
        ):
            self.endpoint = endpoint
            self.secure = secure
            self.objects = set()
            self.upload = None
            self.removed = None
            created_clients.append(self)

        def bucket_exists(self, bucket: str) -> bool:
            assert bucket == "audio"
            return False

        def make_bucket(self, bucket: str) -> None:
            assert bucket == "audio"

        def fput_object(
            self,
            bucket: str,
            object_key: str,
            source_path: str,
            content_type: str,
        ) -> None:
            self.upload = (bucket, object_key, source_path, content_type)
            self.objects.add(object_key)

        def stat_object(self, bucket: str, object_key: str) -> None:
            assert bucket == "audio"
            assert object_key in self.objects

        def remove_object(self, bucket: str, object_key: str) -> None:
            self.removed = (bucket, object_key)
            self.objects.discard(object_key)

        def presigned_get_object(
            self,
            bucket: str,
            object_key: str,
            expires,
            response_headers,
        ) -> str:
            assert bucket == "audio"
            assert response_headers["response-content-type"] == "audio/wav"
            assert "attachment" in response_headers["response-content-disposition"]
            return f"http://{self.endpoint}/{bucket}/{object_key}?signed=true"

    monkeypatch.setattr("app.storage.Minio", FakeMinioClient)
    storage = MinioAudioStorage(
        endpoint="minio:9000",
        access_key="access",
        secret_key="secret",
        bucket="audio",
        secure=False,
        public_endpoint="http://127.0.0.1:9000",
        region="us-east-1",
    )

    source_path = tmp_path / "job123.wav"
    source_path.write_bytes(b"wave-data")

    storage.initialize()
    storage.put_file(source_path, "job123.wav")
    assert storage.exists("job123.wav") is True
    signed_url = storage.presigned_get_url("job123.wav", "job123.wav")
    storage.delete("job123.wav")

    assert [client.endpoint for client in created_clients] == [
        "minio:9000",
        "127.0.0.1:9000",
    ]
    assert created_clients[0].upload == (
        "audio",
        "job123.wav",
        str(source_path),
        "audio/wav",
    )
    assert signed_url == "http://127.0.0.1:9000/audio/job123.wav?signed=true"
    assert created_clients[0].removed == ("audio", "job123.wav")


def test_audio_object_key_rejects_paths():

    import pytest

    with pytest.raises(ValueError, match="plain WAV"):
        validate_audio_object_key("../job123.wav")
