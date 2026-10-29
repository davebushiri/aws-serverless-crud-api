"""End-to-end tests through the local HTTP API.

Request path: HTTP -> `sam local start-api` -> Lambda container (Python 3.14)
-> DynamoDB Local container. Start the stack first with `make local-up`.

Every test starts with an empty table. Only localhost endpoints are allowed.
"""

import json
import os
import urllib.error
import urllib.request

import pytest

import local_table

pytestmark = pytest.mark.integration

API_URL = local_table.require_local(os.environ.get("LOCAL_API_URL", "http://127.0.0.1:3000"))


def call(method, path, body=None):
    """Send a request and return (status, parsed JSON or raw text)."""
    data = body.encode() if isinstance(body, str) else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(API_URL + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status, raw = resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read().decode()
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, raw


def assert_function_error(status, body, error_type):
    """The Lambda raised `error_type` instead of returning a response.

    API Gateway turns this into HTTP 500. `sam local start-api` instead returns
    HTTP 200 with the Lambda error payload, so accept either form.
    """
    if status >= 500:
        return
    assert isinstance(body, dict), f"expected a Lambda error payload, got HTTP {status}: {body!r}"
    assert body.get("errorType") == error_type


@pytest.fixture(scope="session", autouse=True)
def local_stack_running():
    try:
        urllib.request.urlopen(API_URL + "/items", timeout=5)
    except (urllib.error.URLError, ConnectionError) as e:
        pytest.fail(f"Local API not reachable at {API_URL} ({e}). Run `make local-up` first.")


@pytest.fixture(autouse=True)
def empty_table():
    local_table.reset_table()
    yield


def test_crud_workflow():
    # Create
    assert call("PUT", "/items", {"id": "it-1", "price": 19.99, "name": "Widget"}) == (200, "Put item it-1")
    # Retrieve
    assert call("GET", "/items/it-1") == (200, [{"price": 19.99, "id": "it-1", "name": "Widget"}])
    # Retrieve all
    assert call("GET", "/items") == (200, [[{"price": 19.99, "id": "it-1", "name": "Widget"}]])
    # Update (PUT replaces the whole item)
    assert call("PUT", "/items", {"id": "it-1", "price": 24.5, "name": "Widget Pro"}) == (200, "Put item it-1")
    # Retrieve updated
    assert call("GET", "/items/it-1") == (200, [{"price": 24.5, "id": "it-1", "name": "Widget Pro"}])
    # Delete
    assert call("DELETE", "/items/it-1") == (200, "Deleted item it-1")
    # Confirm deletion (baseline returns 400 for a missing item)
    assert call("GET", "/items/it-1") == (400, "Unsupported route: GET /items/{id}")
    assert call("GET", "/items") == (200, [])


def test_each_test_starts_with_empty_table():
    assert call("GET", "/items") == (200, [])


def test_lambda_reads_data_written_directly_to_dynamodb_local():
    local_table.local_client().put_item(
        TableName=local_table.TABLE_NAME,
        Item={"id": {"S": "direct"}, "price": {"N": "7"}, "name": {"S": "seeded"}},
    )
    assert call("GET", "/items/direct") == (200, [{"price": 7.0, "id": "direct", "name": "seeded"}])


def test_get_missing_item_returns_400():
    assert call("GET", "/items/does-not-exist") == (400, "Unsupported route: GET /items/{id}")


def test_put_missing_field_returns_400():
    assert call("PUT", "/items", {"id": "x", "price": 1}) == (400, "Unsupported route: PUT /items")
    assert call("GET", "/items") == (200, [])


def test_put_malformed_json_fails_in_function():
    status, body = call("PUT", "/items", "{not json")
    assert_function_error(status, body, "JSONDecodeError")


def test_put_non_numeric_price_fails_in_function():
    status, body = call("PUT", "/items", {"id": "p", "price": "abc", "name": "n"})
    assert_function_error(status, body, "InvalidOperation")
    assert call("GET", "/items") == (200, [])


def test_delete_missing_item_returns_200():
    assert call("DELETE", "/items/never-existed") == (200, "Deleted item never-existed")


def test_undefined_route_is_not_routed_to_lambda():
    status, _ = call("PATCH", "/items")
    # 403 from sam local, 404 from API Gateway HTTP API.
    assert status in (403, 404)


def test_database_failure_missing_table():
    local_table.delete_table()
    status, body = call("GET", "/items")
    assert_function_error(status, body, "ResourceNotFoundException")
    status, body = call("PUT", "/items", {"id": "a", "price": 1, "name": "n"})
    assert_function_error(status, body, "ResourceNotFoundException")
