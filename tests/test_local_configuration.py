"""Endpoint selection and local-only safeguards. Builds clients only; no network calls."""

import pytest

import local_table
from items_api.repository import table_from_env

AWS_ENDPOINT = "https://dynamodb.us-east-1.amazonaws.com"


def _endpoint(table):
    return table.meta.client.meta.endpoint_url


def test_without_local_endpoint_uses_regular_aws_endpoint(monkeypatch):
    monkeypatch.setenv("TABLE_NAME", "t")
    monkeypatch.delenv("DYNAMODB_ENDPOINT_URL", raising=False)
    assert _endpoint(table_from_env()) == AWS_ENDPOINT


def test_empty_local_endpoint_uses_regular_aws_endpoint(monkeypatch):
    # The deployed template sets DYNAMODB_ENDPOINT_URL to ''.
    monkeypatch.setenv("TABLE_NAME", "t")
    monkeypatch.setenv("DYNAMODB_ENDPOINT_URL", "")
    assert _endpoint(table_from_env()) == AWS_ENDPOINT


def test_local_endpoint_is_used_when_set(monkeypatch):
    monkeypatch.setenv("TABLE_NAME", "t")
    monkeypatch.setenv("DYNAMODB_ENDPOINT_URL", "http://items-dynamodb-local:8000")
    assert _endpoint(table_from_env()) == "http://items-dynamodb-local:8000"


@pytest.mark.parametrize("url", ["http://127.0.0.1:8000", "http://localhost:3000"])
def test_local_helper_accepts_localhost(url):
    assert local_table.require_local(url) == url


@pytest.mark.parametrize("url", [AWS_ENDPOINT, "https://abc123.execute-api.us-east-2.amazonaws.com", "http://10.0.0.5:8000"])
def test_local_helper_refuses_non_local_endpoints(url):
    with pytest.raises(RuntimeError):
        local_table.require_local(url)
