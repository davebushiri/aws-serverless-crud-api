"""Compatibility with the original tutorial Lambda (baseline/lambda_function.py).

Milestone 1 proved the refactor was response-for-response identical to the
baseline. Contract v2 (Milestone 4) intentionally changes error handling, so
every scenario step must now either match the baseline exactly or match an
explicitly listed v2 change. Any other difference fails.

Both run against a fresh in-memory DynamoDB (moto); no AWS calls are made.
"""

import importlib.util
import json
import pathlib

from moto import mock_aws

from conftest import create_items_table, http_event
from items_api import handler
from items_api.repository import DynamoDBItemRepository
from items_api.service import ItemService

BASELINE_PATH = pathlib.Path(__file__).resolve().parents[1] / "baseline" / "lambda_function.py"
BASELINE_TABLE = "http-crud-tutorial-items"  # hard-coded in the baseline

SCENARIO = [
    http_event("GET /items"),
    http_event("PUT /items", body={"id": "123", "price": 12345, "name": "myitem"}),
    http_event("PUT /items", body={"id": "abc", "price": "19.99", "name": "widget"}),
    http_event("PUT /items", body={"id": "flt", "price": 0.1, "name": "cheap"}),
    http_event("GET /items/{id}", item_id="123"),
    http_event("GET /items"),
    http_event("GET /items/{id}", item_id="does-not-exist"),
    http_event("PUT /items", body={"id": "x", "price": 1}),
    http_event("PUT /items", body="not json"),
    http_event("PUT /items", body={"id": "bad", "price": "abc", "name": "n"}),
    http_event("PUT /items", body={"id": 5, "price": 1, "name": "numeric id"}),
    {"version": "2.0", "routeKey": "GET /items/{id}"},
    http_event("DELETE /items/{id}", item_id="123"),
    http_event("DELETE /items/{id}", item_id="never-existed"),
    http_event("GET /items"),
    http_event("PATCH /items"),
    {"version": "2.0"},
]


def _error(status, code, message, extra_headers=None):
    return ("response", {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", **(extra_headers or {})},
        "body": json.dumps({"error": {"code": code, "message": message}}),
    })


def _without_item(item_id):
    """v2 rejects the string-priced 'abc' item, so later listings lack it."""
    def transform(baseline_result):
        kind, response = baseline_result
        items = [entry for entry in json.loads(response["body"]) if entry[0]["id"] != item_id]
        return kind, {**response, "body": json.dumps(items)}
    return transform


PRICE_NOT_NUMBER = "'price' must be a number."
ID_RULE = "'id' must be 1-64 characters using letters, digits, '.', '_', '~' or '-'."

# Intentional contract-v2 changes, by scenario step. Steps not listed must match the baseline.
V2_CHANGES = {
    2: _error(400, "VALIDATION_ERROR", PRICE_NOT_NUMBER),                 # v1 accepted a string price
    5: _without_item("abc"),
    6: _error(404, "ITEM_NOT_FOUND", "Item not found."),                  # v1: 400 "Unsupported route"
    7: _error(400, "VALIDATION_ERROR", "Missing required field(s): name."),
    8: _error(400, "INVALID_JSON", "Request body must be valid JSON."),   # v1: unhandled JSONDecodeError
    9: _error(400, "VALIDATION_ERROR", PRICE_NOT_NUMBER),                 # v1: unhandled InvalidOperation
    10: _error(400, "VALIDATION_ERROR", ID_RULE),                         # v1: unhandled ClientError
    11: _error(400, "VALIDATION_ERROR", "Path parameter 'id' is required."),
    13: _error(404, "ITEM_NOT_FOUND", "Item not found."),                 # v1: 200 for a missing id
    14: _without_item("abc"),
    15: _error(405, "METHOD_NOT_ALLOWED", "Method not allowed for this route.", {"Allow": "GET, PUT"}),  # v1: 200 {}
    16: _error(404, "ROUTE_NOT_FOUND", "Route not found."),               # v1: unhandled KeyError
}


def _call(fn, event):
    try:
        return ("response", fn(event, None))
    except Exception as exc:  # compare failure types, as Lambda would surface them
        return ("raised", type(exc).__name__)


def _run_baseline():
    with mock_aws():
        create_items_table(BASELINE_TABLE)
        spec = importlib.util.spec_from_file_location("baseline_lambda", BASELINE_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return [_call(module.lambda_handler, e) for e in SCENARIO]


def _run_current():
    with mock_aws():
        table = create_items_table("items-under-test")
        handler.set_service(ItemService(DynamoDBItemRepository(table)))
        return [_call(handler.lambda_handler, e) for e in SCENARIO]


def test_current_handler_matches_baseline_except_documented_v2_changes():
    baseline = _run_baseline()
    current = _run_current()
    assert len(baseline) == len(current) == len(SCENARIO)
    for i, (base, actual) in enumerate(zip(baseline, current)):
        change = V2_CHANGES.get(i)
        expected = change(base) if callable(change) else (change or base)
        assert actual == expected, f"step {i} ({SCENARIO[i].get('routeKey')}) differs"


def test_success_steps_are_unchanged():
    unchanged = [i for i in range(len(SCENARIO)) if i not in V2_CHANGES]
    baseline, current = _run_baseline(), _run_current()
    for i in unchanged:
        assert current[i] == baseline[i]
    assert unchanged == [0, 1, 3, 4, 12]  # empty list, valid PUTs, GET, DELETE of an existing item


def test_scenario_covers_documented_baseline_quirks():
    """Pin the baseline (contract v1) behaviors, so a change in the evidence is noticed."""
    results = _run_baseline()
    assert results[4][1]["body"] == '[{"price": 12345.0, "id": "123", "name": "myitem"}]'
    assert results[6][1]["statusCode"] == 400  # missing item -> 400, not 404
    assert results[7][1]["statusCode"] == 400  # missing field -> 400
    assert results[8] == ("raised", "JSONDecodeError")  # invalid JSON -> Lambda error (HTTP 500)
    assert results[13][1]["statusCode"] == 200  # deleting a missing id still succeeds
    assert results[15][1] == {"statusCode": 200, "headers": {"Content-Type": "application/json"}, "body": "{}"}
    assert results[16] == ("raised", "KeyError")  # no routeKey at all


def test_handler_reads_table_name_from_environment(monkeypatch):
    with mock_aws():
        create_items_table("table-from-env")
        monkeypatch.setenv("TABLE_NAME", "table-from-env")
        handler.lambda_handler(http_event("PUT /items", body={"id": "e1", "price": 2, "name": "env"}), None)
        response = handler.lambda_handler(http_event("GET /items/{id}", item_id="e1"), None)
    assert response["statusCode"] == 200
    assert response["body"] == '[{"price": 2.0, "id": "e1", "name": "env"}]'
