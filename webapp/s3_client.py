"""S3 client utilities for the LogViz JSON viewer."""

from __future__ import annotations

import json
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError, NoCredentialsError


class S3Client:
    """Wrapper around boto3 S3 client with helpers for browsing jornadas-detail files."""

    def __init__(
        self,
        bucket: str,
        prefix: str = "jornadas/detail",
        region: str | None = None,
        profile: str | None = None,
    ) -> None:
        self.bucket = bucket
        self.prefix = prefix.rstrip("/")
        session_kwargs: dict[str, Any] = {}
        if region:
            session_kwargs["region_name"] = region
        if profile:
            session_kwargs["profile_name"] = profile
        session = boto3.Session(**session_kwargs)
        self._s3 = session.client("s3")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_partitions(self) -> list[str]:
        """Return the list of date partitions under *prefix* (e.g. ``data=2024-06-15``)."""
        return self._list_common_prefixes(f"{self.prefix}/")

    def list_files(self, partition: str) -> list[str]:
        """Return file names (keys) inside *partition* (e.g. ``J12345.json``)."""
        folder = f"{self.prefix}/{partition}/"
        response = self._s3.list_objects_v2(Bucket=self.bucket, Prefix=folder)
        keys = [
            obj["Key"].split("/")[-1]
            for obj in response.get("Contents", [])
            if not obj["Key"].endswith("/")
        ]
        return sorted(keys)

    def get_json(self, partition: str, filename: str) -> dict[str, Any]:
        """Download and parse a JSON file from S3."""
        key = f"{self.prefix}/{partition}/{filename}"
        try:
            response = self._s3.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            raise FileNotFoundError(
                f"s3://{self.bucket}/{key} not found: {exc}"
            ) from exc
        body = response["Body"].read()
        return json.loads(body)

    def get_raw(self, partition: str, filename: str) -> bytes:
        """Download raw bytes for a file (used for download button)."""
        key = f"{self.prefix}/{partition}/{filename}"
        try:
            response = self._s3.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            raise FileNotFoundError(
                f"s3://{self.bucket}/{key} not found: {exc}"
            ) from exc
        return response["Body"].read()

    def generate_presigned_url(
        self, partition: str, filename: str, expires_in: int = 3600
    ) -> str:
        """Generate a pre-signed URL for direct download."""
        key = f"{self.prefix}/{partition}/{filename}"
        url: str = self._s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
        )
        return url

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _list_common_prefixes(self, prefix: str) -> list[str]:
        paginator = self._s3.get_paginator("list_objects_v2")
        result: list[str] = []
        for page in paginator.paginate(
            Bucket=self.bucket, Prefix=prefix, Delimiter="/"
        ):
            for cp in page.get("CommonPrefixes", []):
                # Strip trailing slash and return only the last segment
                part = cp["Prefix"].rstrip("/").split("/")[-1]
                result.append(part)
        return sorted(result)


def build_client_from_env() -> S3Client:
    """Build an :class:`S3Client` from environment variables.

    Environment variables
    ---------------------
    S3_BUCKET   : required — S3 bucket name
    S3_PREFIX   : optional — prefix inside the bucket (default: ``jornadas/detail``)
    AWS_REGION  : optional — AWS region
    AWS_PROFILE : optional — named AWS profile from ``~/.aws/credentials``
    """
    bucket = os.environ.get("S3_BUCKET", "")
    if not bucket:
        raise ValueError(
            "Environment variable S3_BUCKET is required but not set."
        )
    prefix = os.environ.get("S3_PREFIX", "jornadas/detail")
    region = os.environ.get("AWS_REGION") or None
    profile = os.environ.get("AWS_PROFILE") or None
    return S3Client(bucket=bucket, prefix=prefix, region=region, profile=profile)
