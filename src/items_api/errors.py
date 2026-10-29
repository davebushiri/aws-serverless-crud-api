"""API errors. Each maps to an HTTP status and a stable, machine-readable code.

`message` is safe to return to clients. Internal details go in `detail`,
which is logged but never included in a response.
"""


class ApiError(Exception):
    status = 500
    code = "INTERNAL_ERROR"
    default_message = "An unexpected error occurred."

    def __init__(self, message=None, *, detail=None):
        self.message = message or self.default_message
        self.detail = detail
        super().__init__(detail or self.message)


class InvalidJsonError(ApiError):
    status = 400
    code = "INVALID_JSON"
    default_message = "Request body must be a valid JSON object."


class ValidationError(ApiError):
    status = 400
    code = "VALIDATION_ERROR"
    default_message = "Request is invalid."


class ItemNotFoundError(ApiError):
    status = 404
    code = "ITEM_NOT_FOUND"
    default_message = "Item not found."


class RouteNotFoundError(ApiError):
    status = 404
    code = "ROUTE_NOT_FOUND"
    default_message = "Route not found."


class MethodNotAllowedError(ApiError):
    status = 405
    code = "METHOD_NOT_ALLOWED"
    default_message = "Method not allowed for this route."

    def __init__(self, allowed_methods):
        super().__init__()
        self.allowed_methods = sorted(allowed_methods)


class PayloadTooLargeError(ApiError):
    status = 413
    code = "PAYLOAD_TOO_LARGE"
    default_message = "Request body is too large."


class DependencyUnavailableError(ApiError):
    status = 503
    code = "SERVICE_UNAVAILABLE"
    default_message = "The service is temporarily unavailable. Please retry."
