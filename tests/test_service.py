"""Business logic tests with an in-memory repository: no boto3, no AWS, no mocks."""

from decimal import Decimal

import pytest

from items_api.errors import ItemNotFoundError, ValidationError
from items_api.service import ItemService, parse_item


class InMemoryRepository:
    def __init__(self):
        self.items = {}

    def get(self, item_id):
        return self.items.get(item_id)

    def scan(self):
        return list(self.items.values())

    def put(self, item):
        self.items[item["id"]] = item

    def delete(self, item_id):
        if item_id not in self.items:
            raise ItemNotFoundError()
        del self.items[item_id]


@pytest.fixture
def service_and_repo():
    repo = InMemoryRepository()
    return ItemService(repo), repo


def test_put_stores_price_as_decimal(service_and_repo):
    service, repo = service_and_repo
    assert service.put_item({"id": "a", "price": 0.1, "name": "n"}) == "Put item a"
    assert repo.items["a"]["price"] == Decimal("0.1")


def test_get_returns_single_item_wrapped_in_list(service_and_repo):
    service, _ = service_and_repo
    service.put_item({"id": "a", "price": 3, "name": "n"})
    assert service.get_item("a") == [{"price": 3.0, "id": "a", "name": "n"}]


def test_get_missing_item_raises(service_and_repo):
    service, _ = service_and_repo
    with pytest.raises(ItemNotFoundError):
        service.get_item("missing")


def test_list_returns_list_of_single_item_lists(service_and_repo):
    service, _ = service_and_repo
    service.put_item({"id": "a", "price": 1, "name": "n"})
    assert service.list_items() == [[{"price": 1.0, "id": "a", "name": "n"}]]


def test_put_missing_field_raises_validation_error(service_and_repo):
    service, repo = service_and_repo
    with pytest.raises(ValidationError, match="name"):
        service.put_item({"id": "a", "price": 1})
    assert repo.items == {}


def test_delete_missing_item_raises(service_and_repo):
    service, _ = service_and_repo
    with pytest.raises(ItemNotFoundError):
        service.delete_item("nope")


@pytest.mark.parametrize("price, stored", [(0, Decimal("0")), (12345, Decimal("12345")), (19.99, Decimal("19.99")),
                                           (1000000, Decimal("1000000")), (100.0, Decimal("100.0"))])
def test_valid_prices(price, stored):
    assert parse_item({"id": "a", "price": price, "name": "n"})["price"] == stored


@pytest.mark.parametrize("item_id", ["a", "A-1", "x_y.z~", "9" * 64])
def test_valid_ids(item_id):
    assert parse_item({"id": item_id, "price": 1, "name": "n"})["id"] == item_id


@pytest.mark.parametrize("price", [float("inf"), float("nan"), -0.01, "5", None, [1]])
def test_invalid_prices(price):
    with pytest.raises(ValidationError):
        parse_item({"id": "a", "price": price, "name": "n"})
