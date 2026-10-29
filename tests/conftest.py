"""Test isolation: fake credentials and no access to real AWS config or profiles.

Set before boto3 creates any client, so a test that escapes the moto mock
fails instead of reaching a real AWS account.
"""

import json
import os

os.environ.update({
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_SESSION_TOKEN": "testing",
    "AWS_DEFAULT_REGION": "us-east-1",
    "AWS_CONFIG_FILE": os.devnull,
    "AWS_SHARED_CREDENTIALS_FILE": os.devnull,
})
os.environ.pop("AWS_PROFILE", None)

import boto3  # noqa: E402
import pytest  # noqa: E402


def create_items_table(name):
    dynamodb = boto3.resource("dynamodb")
    return dynamodb.create_table(
        TableName=name,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
        KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
    )


def http_event(route_key, item_id=None, body=None):
    """Minimal API Gateway HTTP API (payload format 2.0) event."""
    method, path = route_key.split(" ", 1)
    event = {
        "version": "2.0",
        "routeKey": route_key,
        "rawPath": path.replace("{id}", item_id or ""),
        "headers": {"content-type": "application/json"},
        "requestContext": {"http": {"method": method, "path": path}},
        "isBase64Encoded": False,
    }
    if item_id is not None:
        event["pathParameters"] = {"id": item_id}
    if body is not None:
        event["body"] = body if isinstance(body, str) else json.dumps(body)
    return event


@pytest.fixture(autouse=True)
def _reset_handler_service():
    from items_api import handler

    handler.set_service(None)
    yield
    handler.set_service(None)
