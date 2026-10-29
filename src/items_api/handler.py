"""Lambda entry point: translates HTTP API (payload v2.0) events to service calls.

Every response is an explicit Lambda proxy object. Errors use the contract-v2
format {"error": {"code": ..., "message": ...}} and never include stack traces
or internal details.
"""

import base64
import binascii
import json
import logging

from .errors import (
    ApiError,
    InvalidJsonError,
    MethodNotAllowedError,
    PayloadTooLargeError,
    RouteNotFoundError,
    ValidationError,
)
from .repository import DynamoDBItemRepository, table_from_env
from .service import ItemService

logger = logging.getLogger()
logger.setLevel(logging.INFO)

HEADERS = {"Content-Type": "application/json"}
MAX_BODY_BYTES = 8 * 1024
INTERNAL_ERROR_BODY = {"error": {"code": ApiError.code, "message": ApiError.default_message}}

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


def _reject_json_constant(name):
    raise ValueError(f"{name} is not allowed")


def parse_json_body(event):
    """Return the request body as a dict, enforcing size, encoding and JSON shape."""
    body = event.get("body")
    if not body:
        raise InvalidJsonError("Request body is required.")
    if len(body) > 2 * MAX_BODY_BYTES:  # cheap early reject before decoding
        raise PayloadTooLargeError(f"Request body must be at most {MAX_BODY_BYTES} bytes.")
    if event.get("isBase64Encoded"):
        try:
            raw = base64.b64decode(body, validate=True)
        except (binascii.Error, ValueError):
            raise InvalidJsonError("Request body is not valid base64.") from None
    else:
        raw = body.encode("utf-8")
    if len(raw) > MAX_BODY_BYTES:
        raise PayloadTooLargeError(f"Request body must be at most {MAX_BODY_BYTES} bytes.")
    try:
        data = json.loads(raw.decode("utf-8"), parse_constant=_reject_json_constant)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise InvalidJsonError("Request body must be valid JSON.") from None
    if not isinstance(data, dict):
        raise InvalidJsonError("Request body must be a JSON object.")
    return data


def _path_id(event):
    item_id = (event.get("pathParameters") or {}).get("id")
    if item_id is None:
        raise ValidationError("Path parameter 'id' is required.")
    return item_id


ROUTES = {
    ("GET", "/items"): lambda event, service: service.list_items(),
    ("PUT", "/items"): lambda event, service: service.put_item(parse_json_body(event)),
    ("GET", "/items/{id}"): lambda event, service: service.get_item(_path_id(event)),
    ("DELETE", "/items/{id}"): lambda event, service: service.delete_item(_path_id(event)),
}


def _dispatch(event, service):
    method, _, path = str(event.get("routeKey", "")).partition(" ")
    route = ROUTES.get((method, path))
    if route is None:
        allowed = [m for (m, p) in ROUTES if p == path]
        raise MethodNotAllowedError(allowed) if allowed else RouteNotFoundError()
    return route(event, service)


def _response(status_code, body, extra_headers=None):
    return {"statusCode": status_code, "headers": {**HEADERS, **(extra_headers or {})}, "body": json.dumps(body)}


def lambda_handler(event, context):
    route_key = event.get("routeKey")
    request_id = (event.get("requestContext") or {}).get("requestId")
    try:
        response = _response(200, _dispatch(event, get_service()))
    except ApiError as e:
        headers = {"Allow": ", ".join(e.allowed_methods)} if isinstance(e, MethodNotAllowedError) else None
        response = _response(e.status, {"error": {"code": e.code, "message": e.message}}, headers)
        log = logger.warning if e.status >= 500 else logger.info
        log("request failed route=%s requestId=%s status=%s code=%s detail=%s",
            route_key, request_id, e.status, e.code, e.detail)
    except Exception:
        # Full traceback goes to the function log only; the client gets a generic body.
        logger.exception("unhandled error route=%s requestId=%s", route_key, request_id)
        response = _response(500, INTERNAL_ERROR_BODY)
    # Never log the event itself: it carries headers, source IP and the request body.
    logger.info("route=%s requestId=%s status=%s", route_key, request_id, response["statusCode"])
    return response
