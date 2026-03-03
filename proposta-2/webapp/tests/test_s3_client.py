"""Unit tests for s3_client.py using mocked boto3."""

from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from s3_client import S3Client, build_client_from_env


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_s3():
    """Patch boto3.Session so no real AWS calls are made."""
    with patch("s3_client.boto3.Session") as mock_session_cls:
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_client = MagicMock()
        mock_session.client.return_value = mock_client
        yield mock_client


@pytest.fixture()
def client(mock_s3) -> S3Client:
    return S3Client(bucket="test-bucket", prefix="jornadas/detail")


# ---------------------------------------------------------------------------
# S3Client.list_partitions
# ---------------------------------------------------------------------------


class TestListPartitions:
    def test_returns_sorted_partition_names(self, client, mock_s3):
        paginator = MagicMock()
        mock_s3.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {
                "CommonPrefixes": [
                    {"Prefix": "jornadas/detail/data=2024-07-20/"},
                    {"Prefix": "jornadas/detail/data=2024-06-15/"},
                ]
            }
        ]

        result = client.list_partitions()

        assert result == ["data=2024-06-15", "data=2024-07-20"]

    def test_returns_empty_list_when_no_partitions(self, client, mock_s3):
        paginator = MagicMock()
        mock_s3.get_paginator.return_value = paginator
        paginator.paginate.return_value = [{"CommonPrefixes": []}]

        result = client.list_partitions()

        assert result == []

    def test_uses_correct_bucket_and_prefix(self, client, mock_s3):
        paginator = MagicMock()
        mock_s3.get_paginator.return_value = paginator
        paginator.paginate.return_value = [{}]

        client.list_partitions()

        paginator.paginate.assert_called_once_with(
            Bucket="test-bucket",
            Prefix="jornadas/detail/",
            Delimiter="/",
        )


# ---------------------------------------------------------------------------
# S3Client.list_files
# ---------------------------------------------------------------------------


class TestListFiles:
    def test_returns_sorted_file_names(self, client, mock_s3):
        mock_s3.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "jornadas/detail/data=2024-06-15/J12346.json"},
                {"Key": "jornadas/detail/data=2024-06-15/J12345.json"},
            ]
        }

        result = client.list_files("data=2024-06-15")

        assert result == ["J12345.json", "J12346.json"]

    def test_skips_directory_entries(self, client, mock_s3):
        mock_s3.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "jornadas/detail/data=2024-06-15/"},
                {"Key": "jornadas/detail/data=2024-06-15/J12345.json"},
            ]
        }

        result = client.list_files("data=2024-06-15")

        assert result == ["J12345.json"]

    def test_returns_empty_when_no_contents(self, client, mock_s3):
        mock_s3.list_objects_v2.return_value = {}

        result = client.list_files("data=2024-06-15")

        assert result == []


# ---------------------------------------------------------------------------
# S3Client.get_json
# ---------------------------------------------------------------------------


class TestGetJson:
    def test_parses_and_returns_dict(self, client, mock_s3):
        payload = {"idJornada": "J12345", "data": "2024-06-15"}
        mock_s3.get_object.return_value = {
            "Body": BytesIO(json.dumps(payload).encode())
        }

        result = client.get_json("data=2024-06-15", "J12345.json")

        assert result == payload

    def test_raises_file_not_found_on_client_error(self, client, mock_s3):
        from botocore.exceptions import ClientError

        mock_s3.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}}, "GetObject"
        )

        with pytest.raises(FileNotFoundError, match="J12345.json"):
            client.get_json("data=2024-06-15", "J12345.json")

    def test_uses_correct_s3_key(self, client, mock_s3):
        mock_s3.get_object.return_value = {
            "Body": BytesIO(b'{"idJornada": "J12345"}')
        }

        client.get_json("data=2024-06-15", "J12345.json")

        mock_s3.get_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="jornadas/detail/data=2024-06-15/J12345.json",
        )


# ---------------------------------------------------------------------------
# S3Client.get_raw
# ---------------------------------------------------------------------------


class TestGetRaw:
    def test_returns_bytes(self, client, mock_s3):
        raw_bytes = b'{"idJornada": "J12345"}'
        mock_s3.get_object.return_value = {"Body": BytesIO(raw_bytes)}

        result = client.get_raw("data=2024-06-15", "J12345.json")

        assert result == raw_bytes

    def test_raises_file_not_found_on_client_error(self, client, mock_s3):
        from botocore.exceptions import ClientError

        mock_s3.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}}, "GetObject"
        )

        with pytest.raises(FileNotFoundError):
            client.get_raw("data=2024-06-15", "J12345.json")


# ---------------------------------------------------------------------------
# S3Client.generate_presigned_url
# ---------------------------------------------------------------------------


class TestGeneratePresignedUrl:
    def test_returns_url(self, client, mock_s3):
        mock_s3.generate_presigned_url.return_value = "https://s3.example.com/signed"

        url = client.generate_presigned_url("data=2024-06-15", "J12345.json")

        assert url == "https://s3.example.com/signed"

    def test_passes_correct_params(self, client, mock_s3):
        mock_s3.generate_presigned_url.return_value = "https://s3.example.com/signed"

        client.generate_presigned_url("data=2024-06-15", "J12345.json", expires_in=7200)

        mock_s3.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={
                "Bucket": "test-bucket",
                "Key": "jornadas/detail/data=2024-06-15/J12345.json",
            },
            ExpiresIn=7200,
        )


# ---------------------------------------------------------------------------
# build_client_from_env
# ---------------------------------------------------------------------------


class TestBuildClientFromEnv:
    def test_raises_when_bucket_not_set(self, monkeypatch):
        monkeypatch.delenv("S3_BUCKET", raising=False)
        with pytest.raises(ValueError, match="S3_BUCKET"):
            build_client_from_env()

    def test_builds_client_with_env_vars(self, monkeypatch):
        monkeypatch.setenv("S3_BUCKET", "my-bucket")
        monkeypatch.setenv("S3_PREFIX", "custom/prefix")
        monkeypatch.setenv("AWS_REGION", "sa-east-1")
        monkeypatch.delenv("AWS_PROFILE", raising=False)

        with patch("s3_client.boto3.Session"):
            c = build_client_from_env()

        assert c.bucket == "my-bucket"
        assert c.prefix == "custom/prefix"
