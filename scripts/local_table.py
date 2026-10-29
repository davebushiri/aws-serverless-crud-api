"""Create, reset or wait for the items table in DynamoDB Local.

Only ever talks to a local endpoint, with synthetic credentials passed
explicitly, so real AWS credentials in the environment are never used.

Usage: python scripts/local_table.py {wait|reset|delete}
"""

import os
import sys
import time
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError, EndpointConnectionError

LOCAL_HOSTS = {"localhost", "127.0.0.1"}
ENDPOINT = os.environ.get("LOCAL_DYNAMODB_URL", "http://127.0.0.1:8000")
TABLE_NAME = os.environ.get("LOCAL_TABLE_NAME", "items-local")


def require_local(url):
    host = urlparse(url).hostname
    if host not in LOCAL_HOSTS:
        raise RuntimeError(f"Refusing to use non-local endpoint {url!r}; only {sorted(LOCAL_HOSTS)} are allowed.")
    return url


def local_client():
    return boto3.client(
        "dynamodb",
        endpoint_url=require_local(ENDPOINT),
        region_name="us-east-1",
        aws_access_key_id="local",
        aws_secret_access_key="local",
    )


def wait_until_ready(timeout=60):
    client = local_client()
    deadline = time.monotonic() + timeout
    while True:
        try:
            client.list_tables()
            return
        except EndpointConnectionError:
            if time.monotonic() > deadline:
                raise
            time.sleep(1)


def delete_table(client=None):
    client = client or local_client()
    try:
        client.delete_table(TableName=TABLE_NAME)
        client.get_waiter("table_not_exists").wait(TableName=TABLE_NAME, WaiterConfig={"Delay": 1})
    except client.exceptions.ResourceNotFoundException:
        pass


def reset_table():
    """Drop and recreate the table so every run starts empty."""
    client = local_client()
    delete_table(client)
    client.create_table(
        TableName=TABLE_NAME,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
        KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
    )
    client.get_waiter("table_exists").wait(TableName=TABLE_NAME, WaiterConfig={"Delay": 1})


def main():
    commands = {"wait": wait_until_ready, "reset": reset_table, "delete": delete_table}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        commands[sys.argv[1]]()
    except (ClientError, EndpointConnectionError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    print(f"{sys.argv[1]}: ok ({TABLE_NAME} at {ENDPOINT})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
