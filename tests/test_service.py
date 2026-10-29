"""Business logic tests with an in-memory repository: no boto3, no AWS, no mocks."""

from decimal import Decimal

import pytest

from items_api.service import ItemNotFoundError, ItemService


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
        self.items.pop(item_id, None)


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


def test_put_missing_field_raises_key_error(service_and_repo):
    service, _ = service_and_repo
    with pytest.raises(KeyError):
        service.put_item({"id": "a", "price": 1})


def test_delete_returns_message_even_when_missing(service_and_repo):
    service, _ = service_and_repo
    assert service.delete_item("nope") == "Deleted item nope"
