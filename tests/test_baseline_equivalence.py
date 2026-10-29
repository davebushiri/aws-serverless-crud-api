"""The refactored handler must answer every request exactly like the baseline.

Both run against a fresh in-memory DynamoDB (moto); no AWS calls are made.
"""

import importlib.util
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


def _run_refactored():
    with mock_aws():
        table = create_items_table("items-under-test")
        handler.set_service(ItemService(DynamoDBItemRepository(table)))
        return [_call(handler.lambda_handler, e) for e in SCENARIO]


def test_refactored_handler_matches_baseline():
    baseline = _run_baseline()
    refactored = _run_refactored()
    for i, (expected, actual) in enumerate(zip(baseline, refactored)):
        assert actual == expected, f"step {i} ({SCENARIO[i].get('routeKey')}) differs"
    assert len(baseline) == len(refactored) == len(SCENARIO)


def test_scenario_covers_documented_baseline_quirks():
    """Pin the baseline behaviors the docs describe, so a change is noticed."""
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
