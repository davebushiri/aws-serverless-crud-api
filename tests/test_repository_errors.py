"""DynamoDB error classification in the repository. No network calls."""

import pytest
from botocore.exceptions import ClientError, ConnectTimeoutError, EndpointConnectionError, ReadTimeoutError
from moto import mock_aws

from conftest import create_items_table
from items_api.errors import DependencyUnavailableError, ItemNotFoundError
from items_api.repository import BOTO_CONFIG, DynamoDBItemRepository


def client_error(code, operation="Scan"):
    return ClientError({"Error": {"Code": code, "Message": "internal detail"}}, operation)


class RaisingTable:
    def __init__(self, exc):
        self.exc = exc

    def _raise(self, **_):
        raise self.exc

    get_item = put_item = delete_item = scan = _raise


@pytest.mark.parametrize("exc", [
    client_error("ProvisionedThroughputExceededException"),
    client_error("ThrottlingException"),
    client_error("RequestLimitExceeded"),
    client_error("InternalServerError"),
    client_error("ServiceUnavailable"),
    EndpointConnectionError(endpoint_url="http://localhost:1"),
    ConnectTimeoutError(endpoint_url="http://localhost:1"),
    ReadTimeoutError(endpoint_url="http://localhost:1"),
])
def test_transient_failures_become_dependency_unavailable(exc):
    repo = DynamoDBItemRepository(RaisingTable(exc))
    for call in (repo.scan, lambda: repo.get("a"), lambda: repo.put({"id": "a"}), lambda: repo.delete("a")):
        with pytest.raises(DependencyUnavailableError):
            call()


@pytest.mark.parametrize("code", ["ResourceNotFoundException", "AccessDeniedException", "ValidationException"])
def test_non_transient_client_errors_propagate(code):
    with pytest.raises(ClientError):
        DynamoDBItemRepository(RaisingTable(client_error(code))).scan()


def test_delete_missing_item_raises_not_found():
    with mock_aws():
        repo = DynamoDBItemRepository(create_items_table("t"))
        with pytest.raises(ItemNotFoundError):
            repo.delete("missing")
        repo.put({"id": "present", "price": 1, "name": "n"})
        repo.delete("present")
        assert repo.get("present") is None


def test_boto_timeouts_fit_inside_lambda_timeout():
    worst_case = BOTO_CONFIG.retries["total_max_attempts"] * (BOTO_CONFIG.connect_timeout + BOTO_CONFIG.read_timeout)
    assert worst_case < 6  # template.yaml Timeout
