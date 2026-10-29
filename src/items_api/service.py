"""Business logic and item validation. Knows nothing about Lambda or API Gateway events.

Item schema (contract v2):
  id     string, 1-64 characters from A-Z a-z 0-9 . _ ~ -
  price  JSON number (not a string or boolean), 0 <= price <= 1,000,000,
         at most 2 decimal places
  name   string, 1-200 characters, not only whitespace
No other fields are accepted.
"""

import re
from decimal import Decimal

from .errors import ItemNotFoundError, ValidationError

ITEM_FIELDS = ("id", "price", "name")
ID_PATTERN = re.compile(r"[A-Za-z0-9._~-]{1,64}")
MAX_PRICE = Decimal("1000000")
MAX_NAME_LENGTH = 200


def validate_item_id(item_id):
    if not isinstance(item_id, str) or not ID_PATTERN.fullmatch(item_id):
        raise ValidationError("'id' must be 1-64 characters using letters, digits, '.', '_', '~' or '-'.")
    return item_id


def _validate_price(price):
    if isinstance(price, bool) or not isinstance(price, (int, float)):
        raise ValidationError("'price' must be a number.")
    value = Decimal(str(price))
    if not value.is_finite() or value < 0 or value > MAX_PRICE:
        raise ValidationError("'price' must be between 0 and 1000000.")
    if value.as_tuple().exponent < -2:
        raise ValidationError("'price' must have at most 2 decimal places.")
    return value


def _validate_name(name):
    if not isinstance(name, str) or not name.strip() or len(name) > MAX_NAME_LENGTH:
        raise ValidationError(f"'name' must be a non-empty string of at most {MAX_NAME_LENGTH} characters.")
    return name


def parse_item(payload):
    """Validate a request payload and return the item to store (price as Decimal)."""
    if set(payload) - set(ITEM_FIELDS):
        raise ValidationError("Unknown fields are not allowed. Allowed fields: id, price, name.")
    missing = [field for field in ITEM_FIELDS if field not in payload]
    if missing:
        raise ValidationError("Missing required field(s): " + ", ".join(missing) + ".")
    return {
        "id": validate_item_id(payload["id"]),
        "price": _validate_price(payload["price"]),
        "name": _validate_name(payload["name"]),
    }


def to_response_item(item):
    return {"price": float(item["price"]), "id": item["id"], "name": item["name"]}


class ItemService:
    def __init__(self, repository):
        self._repository = repository

    def get_item(self, item_id):
        item = self._repository.get(validate_item_id(item_id))
        if item is None:
            raise ItemNotFoundError()
        # Success body shape is unchanged from v1: a single item wrapped in a list.
        return [to_response_item(item)]

    def list_items(self):
        # Unchanged from v1: a list of one-element lists.
        return [[to_response_item(item)] for item in self._repository.scan()]

    def put_item(self, payload):
        item = parse_item(payload)
        self._repository.put(item)
        return "Put item " + item["id"]

    def delete_item(self, item_id):
        self._repository.delete(validate_item_id(item_id))
        return "Deleted item " + item_id
