"""Unit tests for athena_client.py using mocked boto3."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from athena_client import AthenaClient, build_athena_client_from_env


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_athena():
    """Patch boto3.Session so no real AWS calls are made."""
    with patch("athena_client.boto3.Session") as mock_session_cls:
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_client = MagicMock()
        mock_session.client.return_value = mock_client
        yield mock_client


@pytest.fixture()
def client(mock_athena) -> AthenaClient:
    return AthenaClient(
        database="eventos_db",
        workgroup="primary",
        output_location="s3://bucket/results/",
    )


# ---------------------------------------------------------------------------
# AthenaClient.start_query
# ---------------------------------------------------------------------------


class TestStartQuery:
    def test_returns_execution_id(self, client, mock_athena):
        mock_athena.start_query_execution.return_value = {
            "QueryExecutionId": "exec-123"
        }

        result = client.start_query("SELECT 1")

        assert result == "exec-123"

    def test_passes_sql_and_database(self, client, mock_athena):
        mock_athena.start_query_execution.return_value = {
            "QueryExecutionId": "exec-abc"
        }

        client.start_query("SELECT * FROM eventos LIMIT 10")

        call_kwargs = mock_athena.start_query_execution.call_args[1]
        assert call_kwargs["QueryString"] == "SELECT * FROM eventos LIMIT 10"
        assert call_kwargs["QueryExecutionContext"] == {"Database": "eventos_db"}
        assert call_kwargs["WorkGroup"] == "primary"
        assert call_kwargs["ResultConfiguration"] == {
            "OutputLocation": "s3://bucket/results/"
        }

    def test_omits_result_configuration_when_no_output(self, mock_athena):
        client_no_output = AthenaClient(
            database="db", workgroup="primary", output_location=None
        )
        mock_athena.start_query_execution.return_value = {
            "QueryExecutionId": "exec-xyz"
        }

        client_no_output.start_query("SELECT 1")

        call_kwargs = mock_athena.start_query_execution.call_args[1]
        assert "ResultConfiguration" not in call_kwargs


# ---------------------------------------------------------------------------
# AthenaClient.wait_for_query
# ---------------------------------------------------------------------------


class TestWaitForQuery:
    def test_returns_succeeded_immediately(self, client, mock_athena):
        mock_athena.get_query_execution.return_value = {
            "QueryExecution": {"Status": {"State": "SUCCEEDED"}}
        }

        state = client.wait_for_query("exec-123")

        assert state == "SUCCEEDED"

    def test_raises_on_failed_state(self, client, mock_athena):
        mock_athena.get_query_execution.return_value = {
            "QueryExecution": {
                "Status": {
                    "State": "FAILED",
                    "StateChangeReason": "Syntax error",
                }
            }
        }

        with pytest.raises(RuntimeError, match="FAILED"):
            client.wait_for_query("exec-fail")

    def test_raises_on_cancelled_state(self, client, mock_athena):
        mock_athena.get_query_execution.return_value = {
            "QueryExecution": {
                "Status": {
                    "State": "CANCELLED",
                    "StateChangeReason": "User cancelled",
                }
            }
        }

        with pytest.raises(RuntimeError, match="CANCELLED"):
            client.wait_for_query("exec-cancel")

    def test_polls_until_succeeded(self, client, mock_athena):
        mock_athena.get_query_execution.side_effect = [
            {"QueryExecution": {"Status": {"State": "RUNNING"}}},
            {"QueryExecution": {"Status": {"State": "RUNNING"}}},
            {"QueryExecution": {"Status": {"State": "SUCCEEDED"}}},
        ]

        with patch("athena_client.time.sleep") as mock_sleep:
            state = client.wait_for_query("exec-poll")

        assert state == "SUCCEEDED"
        assert mock_sleep.call_count == 2

    def test_raises_timeout(self, client, mock_athena):
        mock_athena.get_query_execution.return_value = {
            "QueryExecution": {"Status": {"State": "RUNNING"}}
        }

        with patch("athena_client._MAX_WAIT", 4), patch("athena_client.time.sleep"):
            with pytest.raises(TimeoutError):
                client.wait_for_query("exec-timeout")


# ---------------------------------------------------------------------------
# AthenaClient.get_results
# ---------------------------------------------------------------------------


class TestGetResults:
    def test_returns_list_of_dicts(self, client, mock_athena):
        paginator = MagicMock()
        mock_athena.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {
                "ResultSet": {
                    "Rows": [
                        {"Data": [{"VarCharValue": "id"}, {"VarCharValue": "canal"}]},
                        {"Data": [{"VarCharValue": "J1"}, {"VarCharValue": "web"}]},
                        {"Data": [{"VarCharValue": "J2"}, {"VarCharValue": "app"}]},
                    ]
                }
            }
        ]

        result = client.get_results("exec-123")

        assert result == [
            {"id": "J1", "canal": "web"},
            {"id": "J2", "canal": "app"},
        ]

    def test_returns_empty_list_for_no_data_rows(self, client, mock_athena):
        paginator = MagicMock()
        mock_athena.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {
                "ResultSet": {
                    "Rows": [
                        {"Data": [{"VarCharValue": "id"}, {"VarCharValue": "canal"}]},
                    ]
                }
            }
        ]

        result = client.get_results("exec-empty")

        assert result == []

    def test_handles_missing_var_char_value(self, client, mock_athena):
        paginator = MagicMock()
        mock_athena.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {
                "ResultSet": {
                    "Rows": [
                        {"Data": [{"VarCharValue": "id"}]},
                        {"Data": [{}]},
                    ]
                }
            }
        ]

        result = client.get_results("exec-null")

        assert result == [{"id": ""}]


# ---------------------------------------------------------------------------
# AthenaClient.run_query
# ---------------------------------------------------------------------------


class TestRunQuery:
    def test_delegates_to_start_wait_get(self, client, mock_athena):
        mock_athena.start_query_execution.return_value = {
            "QueryExecutionId": "exec-full"
        }
        mock_athena.get_query_execution.return_value = {
            "QueryExecution": {"Status": {"State": "SUCCEEDED"}}
        }
        paginator = MagicMock()
        mock_athena.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {
                "ResultSet": {
                    "Rows": [
                        {"Data": [{"VarCharValue": "id"}]},
                        {"Data": [{"VarCharValue": "J99"}]},
                    ]
                }
            }
        ]

        result = client.run_query("SELECT * FROM eventos LIMIT 1")

        assert result == [{"id": "J99"}]


# ---------------------------------------------------------------------------
# build_athena_client_from_env
# ---------------------------------------------------------------------------


class TestBuildAthenaClientFromEnv:
    def test_builds_with_defaults(self, monkeypatch):
        monkeypatch.delenv("ATHENA_DATABASE", raising=False)
        monkeypatch.delenv("ATHENA_WORKGROUP", raising=False)
        monkeypatch.delenv("ATHENA_OUTPUT", raising=False)
        monkeypatch.delenv("AWS_REGION", raising=False)
        monkeypatch.delenv("AWS_PROFILE", raising=False)

        with patch("athena_client.boto3.Session"):
            c = build_athena_client_from_env()

        assert c.database == "eventos_db"
        assert c.workgroup == "primary"
        assert c.output_location is None

    def test_builds_with_env_vars(self, monkeypatch):
        monkeypatch.setenv("ATHENA_DATABASE", "my_db")
        monkeypatch.setenv("ATHENA_WORKGROUP", "my_wg")
        monkeypatch.setenv("ATHENA_OUTPUT", "s3://out/")
        monkeypatch.setenv("AWS_REGION", "sa-east-1")
        monkeypatch.delenv("AWS_PROFILE", raising=False)

        with patch("athena_client.boto3.Session"):
            c = build_athena_client_from_env()

        assert c.database == "my_db"
        assert c.workgroup == "my_wg"
        assert c.output_location == "s3://out/"
