"""Business logic for items. Knows nothing about Lambda or API Gateway events."""

from decimal import Decimal


class ItemNotFoundError(Exception):
    pass


def to_response_item(item):
    # Missing attributes raise KeyError, which the handler turns into a 400,
    # matching the baseline.
    return {"price": float(item["price"]), "id": item["id"], "name": item["name"]}


class ItemService:
    def __init__(self, repository):
        self._repository = repository

    def get_item(self, item_id):
        item = self._repository.get(item_id)
        if item is None:
            raise ItemNotFoundError(item_id)
        # The baseline wraps a single item in a list; kept for compatibility.
        return [to_response_item(item)]

    def list_items(self):
        # The baseline returns a list of one-element lists; kept for compatibility.
        return [[to_response_item(item)] for item in self._repository.scan()]

    def put_item(self, payload):
        self._repository.put({
            "id": payload["id"],
            "price": Decimal(str(payload["price"])),
            "name": payload["name"],
        })
        return "Put item " + payload["id"]

    def delete_item(self, item_id):
        self._repository.delete(item_id)
        return "Deleted item " + item_id
