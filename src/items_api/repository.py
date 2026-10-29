"""DynamoDB access for items. The only module that talks to boto3."""

import os

import boto3


class DynamoDBItemRepository:
    def __init__(self, table):
        self._table = table

    def get(self, item_id):
        """Return the stored item, or None when no item has this id."""
        return self._table.get_item(Key={"id": item_id}).get("Item")

    def scan(self):
        # Single Scan call: returns at most 1 MB of items, same as the baseline.
        return self._table.scan()["Items"]

    def put(self, item):
        self._table.put_item(Item=item)

    def delete(self, item_id):
        self._table.delete_item(Key={"id": item_id})


def table_from_env():
    """Build the DynamoDB table from environment configuration.

    TABLE_NAME is required. DYNAMODB_ENDPOINT_URL is optional and lets local
    runs point at DynamoDB Local instead of AWS.
    """
    endpoint_url = os.environ.get("DYNAMODB_ENDPOINT_URL") or None
    dynamodb = boto3.resource("dynamodb", endpoint_url=endpoint_url)
    return dynamodb.Table(os.environ["TABLE_NAME"])
