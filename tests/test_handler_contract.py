"""Contract v2 at the handler level: status codes, error format, limits, safe logging.

Uses an in-memory repository, so no AWS, moto or Docker is involved.
"""

import base64
import json
import logging

import pytest

from conftest import http_event
from items_api import handler
from items_api.errors import DependencyUnavailableError
from items_api.service import ItemService
from test_service import InMemoryRepository

ERROR_KEYS = {"error"}


@pytest.fixture
def repo():
    repo = InMemoryRepository()
    handler.set_service(ItemService(repo))
    return repo


def invoke(event):
    response = handler.lambda_handler(event, None)
    assert set(response) == {"statusCode", "headers", "body"}
    assert response["headers"]["Content-Type"] == "application/json"
    return response["statusCode"], json.loads(response["body"]), response["headers"]


def assert_error(result, status, code):
    got_status, body, _ = result
    assert got_status == status, body
    assert set(body) == ERROR_KEYS and set(body["error"]) == {"code", "message"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    return body["error"]["message"]


# --- success responses keep the v1 shapes ---

def test_success_shapes_unchanged(repo):
    assert invoke(http_event("PUT /items", body={"id": "a", "price": 19.99, "name": "Widget"}))[:2] == (200, "Put item a")
    assert invoke(http_event("GET /items/{id}", item_id="a"))[:2] == (200, [{"price": 19.99, "id": "a", "name": "Widget"}])
    assert invoke(http_event("GET /items"))[:2] == (200, [[{"price": 19.99, "id": "a", "name": "Widget"}]])
    assert invoke(http_event("DELETE /items/{id}", item_id="a"))[:2] == (200, "Deleted item a")


# --- 400 ---

@pytest.mark.parametrize("body", [None, "", "{not json", "[1, 2]", '"text"', "null", '{"price": NaN}', "[" * 5000])
def test_invalid_json_returns_400(repo, body):
    event = http_event("PUT /items")
    if body is not None:
        event["body"] = body
    assert_error(invoke(event), 400, "INVALID_JSON")


@pytest.mark.parametrize("payload", [
    {"id": "a", "price": 1},                                   # missing name
    {"id": "a", "price": 1, "name": "n", "extra": True},       # unknown field
    {"id": "a", "price": "1", "name": "n"},                    # price as string
    {"id": "a", "price": True, "name": "n"},                   # boolean price
    {"id": "a", "price": -1, "name": "n"},                     # negative
    {"id": "a", "price": 1000000.01, "name": "n"},             # too large
    {"id": "a", "price": 1.234, "name": "n"},                  # >2 decimals
    {"id": 5, "price": 1, "name": "n"},                        # numeric id
    {"id": "has space", "price": 1, "name": "n"},              # bad id characters
    {"id": "x" * 65, "price": 1, "name": "n"},                 # id too long
    {"id": "a", "price": 1, "name": "   "},                    # blank name
    {"id": "a", "price": 1, "name": "n" * 201},                # name too long
])
def test_invalid_item_returns_400_and_stores_nothing(repo, payload):
    assert_error(invoke(http_event("PUT /items", body=payload)), 400, "VALIDATION_ERROR")
    assert repo.items == {}


def test_invalid_path_id_returns_400(repo):
    assert_error(invoke(http_event("GET /items/{id}", item_id="bad id!")), 400, "VALIDATION_ERROR")


def test_base64_body_is_decoded(repo):
    event = http_event("PUT /items")
    event["body"] = base64.b64encode(b'{"id": "b", "price": 2, "name": "n"}').decode()
    event["isBase64Encoded"] = True
    assert invoke(event)[:2] == (200, "Put item b")


def test_invalid_base64_returns_400(repo):
    event = http_event("PUT /items")
    event["body"], event["isBase64Encoded"] = "***", True
    assert_error(invoke(event), 400, "INVALID_JSON")


# --- 404 / 405 / 413 ---

def test_missing_item_returns_404(repo):
    assert_error(invoke(http_event("GET /items/{id}", item_id="nope")), 404, "ITEM_NOT_FOUND")
    assert_error(invoke(http_event("DELETE /items/{id}", item_id="nope")), 404, "ITEM_NOT_FOUND")


def test_unknown_route_returns_404(repo):
    assert_error(invoke(http_event("GET /orders")), 404, "ROUTE_NOT_FOUND")
    assert_error(invoke({"version": "2.0"}), 404, "ROUTE_NOT_FOUND")


def test_wrong_method_returns_405_with_allow_header(repo):
    result = invoke(http_event("PATCH /items"))
    assert_error(result, 405, "METHOD_NOT_ALLOWED")
    assert result[2]["Allow"] == "GET, PUT"


def test_oversized_body_returns_413(repo):
    payload = {"id": "a", "price": 1, "name": "n" * (handler.MAX_BODY_BYTES + 1)}
    assert_error(invoke(http_event("PUT /items", body=payload)), 413, "PAYLOAD_TOO_LARGE")
    assert repo.items == {}


# --- 500 / 503 and safe logging ---

class FailingRepository(InMemoryRepository):
    def __init__(self, exc):
        super().__init__()
        self.exc = exc

    def scan(self):
        raise self.exc


def test_unexpected_exception_returns_generic_500_without_details(caplog):
    handler.set_service(ItemService(FailingRepository(RuntimeError("secret-internal-detail table=prod-items"))))
    with caplog.at_level(logging.INFO):
        status, body, _ = invoke(http_event("GET /items"))
    assert (status, body) == (500, {"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred."}})
    assert "secret-internal-detail" not in json.dumps(body)
    assert "secret-internal-detail" in caplog.text  # kept for operators, server-side only


def test_dependency_unavailable_returns_503_without_details():
    handler.set_service(ItemService(FailingRepository(DependencyUnavailableError(detail="DynamoDB ThrottlingException"))))
    status, body, _ = invoke(http_event("GET /items"))
    assert status == 503 and body["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert "Throttling" not in body["error"]["message"]


def test_request_headers_and_body_are_not_logged(repo, caplog):
    event = http_event("PUT /items", body={"id": "a", "price": 1, "name": "private-name"})
    event["headers"]["authorization"] = "Bearer secret-token-value"
    event["requestContext"]["requestId"] = "req-123"
    with caplog.at_level(logging.DEBUG):
        invoke(event)
    assert "secret-token-value" not in caplog.text
    assert "private-name" not in caplog.text
    assert "requestId=req-123" in caplog.text and "status=200" in caplog.text
