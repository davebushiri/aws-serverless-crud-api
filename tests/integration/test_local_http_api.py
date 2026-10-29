"""End-to-end tests of contract v2 through the local HTTP API.

Request path: HTTP -> `sam local start-api` -> Lambda container (Python 3.14)
-> DynamoDB Local container. Start the stack first with `make local-up`.

Every test starts with an empty table. Only localhost endpoints are allowed.
"""

import json
import os
import subprocess
import urllib.error
import urllib.request

import pytest

import local_table

pytestmark = pytest.mark.integration

API_URL = local_table.require_local(os.environ.get("LOCAL_API_URL", "http://127.0.0.1:3000"))
DDB_CONTAINER = "items-dynamodb-local"
# Text that must never appear in an error response.
LEAK_MARKERS = ("Traceback", "stackTrace", "errorType", "botocore", "ResourceNotFound", "items-local",
                "dynamodb", "/var/task", "arn:aws")


def call(method, path, body=None):
    """Send a request and return (status, parsed JSON or raw text).

    Fails immediately if the response is a leaked Lambda crash payload, which
    sam local returns as HTTP 200 with a stack trace.
    """
    data = body.encode() if isinstance(body, str) else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(API_URL + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status, raw = resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read().decode()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = raw
    if isinstance(parsed, dict) and {"errorType", "stackTrace"} & set(parsed):
        pytest.fail(f"unhandled Lambda error leaked to the client (HTTP {status}): {parsed.get('errorType')}")
    return status, parsed


def assert_error(result, status, code):
    """Exact contract-v2 error: status, {"error": {"code", "message"}} and no internal details."""
    got_status, body = result
    assert got_status == status, f"expected {status} {code}, got {got_status}: {body!r}"
    assert isinstance(body, dict) and set(body) == {"error"} and set(body["error"]) == {"code", "message"}, body
    assert body["error"]["code"] == code
    text = json.dumps(body)
    leaked = [marker for marker in LEAK_MARKERS if marker in text]
    assert not leaked, f"error response exposes internal details {leaked}: {text}"


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


# --- correct application responses ---

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
    # Confirm deletion
    assert_error(call("GET", "/items/it-1"), 404, "ITEM_NOT_FOUND")
    assert_error(call("DELETE", "/items/it-1"), 404, "ITEM_NOT_FOUND")
    assert call("GET", "/items") == (200, [])


def test_each_test_starts_with_empty_table():
    assert call("GET", "/items") == (200, [])


def test_lambda_reads_data_written_directly_to_dynamodb_local():
    local_table.local_client().put_item(
        TableName=local_table.TABLE_NAME,
        Item={"id": {"S": "direct"}, "price": {"N": "7"}, "name": {"S": "seeded"}},
    )
    assert call("GET", "/items/direct") == (200, [{"price": 7.0, "id": "direct", "name": "seeded"}])


# --- expected client errors ---

def test_missing_item_returns_404():
    assert_error(call("GET", "/items/does-not-exist"), 404, "ITEM_NOT_FOUND")
    assert_error(call("DELETE", "/items/does-not-exist"), 404, "ITEM_NOT_FOUND")


@pytest.mark.parametrize("body", ["{not json", "[1, 2]", "", '{"price": NaN}'])
def test_malformed_json_returns_400(body):
    assert_error(call("PUT", "/items", body), 400, "INVALID_JSON")
    assert call("GET", "/items") == (200, [])


@pytest.mark.parametrize("payload", [
    {"id": "x", "price": 1},
    {"id": "p", "price": "abc", "name": "n"},
    {"id": "p", "price": -5, "name": "n"},
    {"id": "p", "price": 1.999, "name": "n"},
    {"id": 5, "price": 1, "name": "n"},
    {"id": "p", "price": 1, "name": "n", "admin": True},
])
def test_invalid_item_returns_400_and_stores_nothing(payload):
    assert_error(call("PUT", "/items", payload), 400, "VALIDATION_ERROR")
    assert call("GET", "/items") == (200, [])


def test_invalid_path_id_returns_400():
    assert_error(call("GET", "/items/bad%20id!"), 400, "VALIDATION_ERROR")


def test_oversized_body_returns_413():
    assert_error(call("PUT", "/items", {"id": "big", "price": 1, "name": "n" * 9000}), 413, "PAYLOAD_TOO_LARGE")
    assert call("GET", "/items") == (200, [])


def test_undefined_route_is_answered_by_the_api_layer():
    # Never reaches the Lambda, so the platform's own response applies (not contract v2).
    assert call("PATCH", "/items") in [
        (403, {"message": "Missing Authentication Token"}),  # sam local start-api
        (404, {"message": "Not Found"}),                      # API Gateway HTTP API
    ]


# --- server-side failures ---

def test_missing_table_returns_generic_500():
    local_table.delete_table()
    assert_error(call("GET", "/items"), 500, "INTERNAL_ERROR")
    assert_error(call("PUT", "/items", {"id": "a", "price": 1, "name": "n"}), 500, "INTERNAL_ERROR")


def _docker(*args):
    subprocess.run(["docker", *args], check=True, capture_output=True, timeout=60)


def test_unavailable_database_returns_503():
    _docker("stop", "--timeout", "2", DDB_CONTAINER)
    try:
        assert_error(call("GET", "/items"), 503, "SERVICE_UNAVAILABLE")
        assert_error(call("PUT", "/items", {"id": "a", "price": 1, "name": "n"}), 503, "SERVICE_UNAVAILABLE")
    finally:
        _docker("start", DDB_CONTAINER)
        local_table.wait_until_ready()
    # Recovers once the database is back (in-memory data is gone, so recreate the table).
    local_table.reset_table()
    assert call("PUT", "/items", {"id": "after", "price": 1, "name": "n"}) == (200, "Put item after")
