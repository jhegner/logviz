"""Athena client utilities for the LogViz query interface."""

from __future__ import annotations

import os
import time
from typing import Any

import boto3
from botocore.exceptions import ClientError


_POLL_INTERVAL = 2  # seconds between status checks
_MAX_WAIT = 300     # max total seconds to wait for a query to finish


class AthenaClient:
    """Wrapper around boto3 Athena client for running SQL queries."""

    def __init__(
        self,
        database: str = "eventos_db",
        workgroup: str = "primary",
        output_location: str | None = None,
        region: str | None = None,
        profile: str | None = None,
    ) -> None:
        self.database = database
        self.workgroup = workgroup
        self.output_location = output_location
        session_kwargs: dict[str, Any] = {}
        if region:
            session_kwargs["region_name"] = region
        if profile:
            session_kwargs["profile_name"] = profile
        session = boto3.Session(**session_kwargs)
        self._athena = session.client("athena")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_query(self, sql: str) -> str:
        """Submit a SQL query to Athena and return the execution ID."""
        kwargs: dict[str, Any] = {
            "QueryString": sql,
            "QueryExecutionContext": {"Database": self.database},
            "WorkGroup": self.workgroup,
        }
        if self.output_location:
            kwargs["ResultConfiguration"] = {
                "OutputLocation": self.output_location
            }
        response = self._athena.start_query_execution(**kwargs)
        return response["QueryExecutionId"]

    def wait_for_query(self, execution_id: str) -> str:
        """Poll until the query finishes. Returns the final state."""
        elapsed = 0
        while elapsed < _MAX_WAIT:
            response = self._athena.get_query_execution(
                QueryExecutionId=execution_id
            )
            state = response["QueryExecution"]["Status"]["State"]
            if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
                if state != "SUCCEEDED":
                    reason = (
                        response["QueryExecution"]["Status"]
                        .get("StateChangeReason", "Unknown error")
                    )
                    raise RuntimeError(
                        f"Athena query {state}: {reason}"
                    )
                return state
            time.sleep(_POLL_INTERVAL)
            elapsed += _POLL_INTERVAL
        raise TimeoutError(
            f"Athena query {execution_id} did not finish within {_MAX_WAIT}s"
        )

    def get_results(self, execution_id: str) -> list[dict[str, str]]:
        """Retrieve all rows from a completed query as a list of dicts."""
        rows: list[dict[str, str]] = []
        paginator = self._athena.get_paginator("get_query_results")
        first_page = True
        headers: list[str] = []

        for page in paginator.paginate(QueryExecutionId=execution_id):
            result_rows = page["ResultSet"]["Rows"]
            if first_page and result_rows:
                # First row of the first page contains column names
                headers = [
                    col.get("VarCharValue", "")
                    for col in result_rows[0]["Data"]
                ]
                result_rows = result_rows[1:]
                first_page = False
            for row in result_rows:
                values = [cell.get("VarCharValue", "") for cell in row["Data"]]
                rows.append(dict(zip(headers, values)))

        return rows

    def run_query(self, sql: str) -> list[dict[str, str]]:
        """Execute *sql*, wait for completion and return results as list of dicts."""
        execution_id = self.start_query(sql)
        self.wait_for_query(execution_id)
        return self.get_results(execution_id)


def build_athena_client_from_env() -> AthenaClient:
    """Build an :class:`AthenaClient` from environment variables.

    Environment variables
    ---------------------
    ATHENA_DATABASE  : optional — Athena database (default: ``eventos_db``)
    ATHENA_WORKGROUP : optional — Athena workgroup (default: ``primary``)
    ATHENA_OUTPUT    : optional — S3 output location for results
    AWS_REGION       : optional — AWS region
    AWS_PROFILE      : optional — named AWS profile
    """
    return AthenaClient(
        database=os.environ.get("ATHENA_DATABASE", "eventos_db"),
        workgroup=os.environ.get("ATHENA_WORKGROUP", "primary"),
        output_location=os.environ.get("ATHENA_OUTPUT") or None,
        region=os.environ.get("AWS_REGION") or None,
        profile=os.environ.get("AWS_PROFILE") or None,
    )
