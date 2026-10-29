"""Lambda entry point: translates HTTP API (payload v2.0) events to service calls."""

import json
import logging

from .repository import DynamoDBItemRepository, table_from_env
from .service import ItemNotFoundError, ItemService

logger = logging.getLogger()
logger.setLevel(logging.INFO)

HEADERS = {"Content-Type": "application/json"}

_service = None


def get_service():
    """Create the service once per Lambda execution environment."""
    global _service
    if _service is None:
        _service = ItemService(DynamoDBItemRepository(table_from_env()))
    return _service


def set_service(service):
    """Replace the service, e.g. with one backed by a test table."""
    global _service
    _service = service


def _dispatch(event, service):
    route_key = event["routeKey"]
    if route_key == "DELETE /items/{id}":
        return service.delete_item(event["pathParameters"]["id"])
    if route_key == "GET /items/{id}":
        return service.get_item(event["pathParameters"]["id"])
    if route_key == "GET /items":
        return service.list_items()
    if route_key == "PUT /items":
        return service.put_item(json.loads(event["body"]))
    # Unknown routes return 200 with an empty object, as in the baseline.
    return {}


def lambda_handler(event, context):
    # Log the route only; the baseline printed the whole event, including headers.
    logger.info("routeKey=%s", event.get("routeKey"))
    status_code = 200
    try:
        body = _dispatch(event, get_service())
    except (KeyError, ItemNotFoundError):
        status_code = 400
        body = "Unsupported route: " + event["routeKey"]
    return {"statusCode": status_code, "headers": dict(HEADERS), "body": json.dumps(body)}
