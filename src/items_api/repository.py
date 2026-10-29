"""DynamoDB access for items. The only module that talks to boto3."""

import os
from contextlib import contextmanager

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, HTTPClientError
from botocore.exceptions import ConnectionError as BotoConnectionError

from .errors import DependencyUnavailableError, ItemNotFoundError

# DynamoDB errors that are temporary and worth retrying from the client side.
TRANSIENT_ERROR_CODES = frozenset({
    "ProvisionedThroughputExceededException",
    "ThrottlingException",
    "RequestLimitExceeded",
    "InternalServerError",
    "ServiceUnavailable",
})

# Bounded so a failing dependency produces a 503 well inside the Lambda timeout:
# at most 2 attempts with 1 s connect and 1 s read timeouts.
BOTO_CONFIG = Config(
    connect_timeout=1,
    read_timeout=1,
    retries={"total_max_attempts": 2, "mode": "standard"},
)


@contextmanager
def _dynamodb_errors():
    """Translate temporary DynamoDB failures into DependencyUnavailableError.

    Anything else (for example a missing table or an access error) propagates
    and becomes a 500, because retrying will not fix it.
    """
    try:
        yield
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in TRANSIENT_ERROR_CODES:
            raise DependencyUnavailableError(detail=f"DynamoDB {code}") from e
        raise
    # Connection refused, DNS failure, connect/read timeouts, dropped connections.
    except (BotoConnectionError, HTTPClientError) as e:
        raise DependencyUnavailableError(detail=f"DynamoDB {type(e).__name__}") from e


class DynamoDBItemRepository:
    def __init__(self, table):
        self._table = table

    def get(self, item_id):
        """Return the stored item, or None when no item has this id."""
        with _dynamodb_errors():
            return self._table.get_item(Key={"id": item_id}).get("Item")

    def scan(self):
        # Single Scan call: returns at most 1 MB of items (no pagination yet).
        with _dynamodb_errors():
            return self._table.scan()["Items"]

    def put(self, item):
        with _dynamodb_errors():
            self._table.put_item(Item=item)

    def delete(self, item_id):
        """Delete an existing item; raise ItemNotFoundError if there is none."""
        try:
            with _dynamodb_errors():
                self._table.delete_item(Key={"id": item_id}, ConditionExpression="attribute_exists(id)")
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                raise ItemNotFoundError() from e
            raise


def table_from_env():
    """Build the DynamoDB table from environment configuration.

    TABLE_NAME is required. DYNAMODB_ENDPOINT_URL is optional and lets local
    runs point at DynamoDB Local instead of AWS.
    """
    endpoint_url = os.environ.get("DYNAMODB_ENDPOINT_URL") or None
    dynamodb = boto3.resource("dynamodb", endpoint_url=endpoint_url, config=BOTO_CONFIG)
    return dynamodb.Table(os.environ["TABLE_NAME"])
