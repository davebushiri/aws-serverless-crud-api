# API contract

**Current: v2** (Milestone 4). v1 is the original tutorial behavior, preserved in `baseline/lambda_function.py`.

Success responses are identical in v1 and v2. v2 changes only invalid requests and failures.

## Routes and success responses (v1 and v2)

| Route | Request | 200 response body |
| --- | --- | --- |
| `PUT /items` | `{"id": "123", "price": 12.5, "name": "x"}` (creates or replaces) | `"Put item 123"` |
| `GET /items/{id}` | | `[{"price": 12.5, "id": "123", "name": "x"}]` (one item in a list) |
| `GET /items` | | `[[{...}], [{...}]]` (a list of one-item lists; one Scan page, at most 1 MB) |
| `DELETE /items/{id}` | | `"Deleted item 123"` |

All responses are `Content-Type: application/json`.

## Item schema (v2)

| Field | Rule |
| --- | --- |
| `id` | String, 1–64 characters from `A–Z a–z 0–9 . _ ~ -`. Applies to the body and the `{id}` path parameter. |
| `price` | JSON number (not a string or boolean), `0 ≤ price ≤ 1,000,000`, at most 2 decimal places. Stored as a DynamoDB number; returned as a float. |
| `name` | String, 1–200 characters, not only whitespace. |
| other fields | Rejected. |

Request body: a JSON object of at most **8 KiB** (base64-encoded bodies are decoded first). `NaN` and `Infinity` are rejected.

## Error format (v2)

```json
{"error": {"code": "VALIDATION_ERROR", "message": "'price' must be a number."}}
```

`code` is stable and machine-readable; `message` is for people and may change. Error responses never contain stack traces, exception names, AWS error codes, table names or other internal details; those go only to the function log.

| Status | `code` | When |
| --- | --- | --- |
| 400 | `INVALID_JSON` | Body missing, not UTF-8 or valid base64, not valid JSON, too deeply nested, or not a JSON object |
| 400 | `VALIDATION_ERROR` | Missing, unknown or wrongly typed field; invalid `id`, `price` or `name`; invalid path `id` |
| 404 | `ITEM_NOT_FOUND` | `GET` or `DELETE` of an id that doesn't exist |
| 404 | `ROUTE_NOT_FOUND` | The Lambda receives an unknown route (only possible by direct invocation; see below) |
| 405 | `METHOD_NOT_ALLOWED` | The Lambda receives a known path with an unsupported method; includes an `Allow` header |
| 413 | `PAYLOAD_TOO_LARGE` | Body larger than 8 KiB |
| 500 | `INTERNAL_ERROR` | Unexpected failure, including a missing table or access error. Not retryable. |
| 503 | `SERVICE_UNAVAILABLE` | DynamoDB throttling, a DynamoDB 5xx, or a connection or timeout failure. Retryable. |

### Requests that never reach the Lambda

API Gateway only forwards the four routes above. Any other method or path is answered by the platform itself, **not** in the v2 format:

| | Response |
| --- | --- |
| API Gateway HTTP API (per AWS docs; not verified in AWS) | `404 {"message":"Not Found"}` |
| `sam local start-api` (verified locally) | `403 {"message":"Missing Authentication Token"}` |

## What changed from v1

| Situation | v1 (original) | v2 |
| --- | --- | --- |
| Missing item on `GET` | `400 "Unsupported route: GET /items/{id}"` | `404 ITEM_NOT_FOUND` |
| Missing item on `DELETE` | `200 "Deleted item …"` | `404 ITEM_NOT_FOUND` (conditional delete) |
| Missing field | `400 "Unsupported route: PUT /items"` | `400 VALIDATION_ERROR`, naming the field |
| Malformed JSON | Unhandled `JSONDecodeError`: API Gateway `500`; sam local `200` + stack trace | `400 INVALID_JSON` |
| Non-numeric `price` (`"abc"`) | Unhandled `InvalidOperation` (as above) | `400 VALIDATION_ERROR` |
| Numeric string `price` (`"19.99"`) | Accepted | `400 VALIDATION_ERROR` (must be a JSON number) |
| Non-string `id` | Unhandled DynamoDB `ValidationException` | `400 VALIDATION_ERROR` |
| Unknown fields | Silently ignored | `400 VALIDATION_ERROR` |
| Negative, huge or 3-decimal `price`, empty `name`, any-length `id` | Accepted | `400 VALIDATION_ERROR` |
| Body over 8 KiB | Accepted (up to API Gateway's 10 MB) | `413 PAYLOAD_TOO_LARGE` |
| Table missing / database error | Unhandled exception with AWS error details in the stack trace | `500 INTERNAL_ERROR`, generic message |
| Database unreachable / throttled | Unhandled exception, or a Lambda timeout after boto3's default retries | `503 SERVICE_UNAVAILABLE` |
| Unknown route inside the Lambda | `200 {}` | `404 ROUTE_NOT_FOUND` / `405 METHOD_NOT_ALLOWED` |
| Logging | Full event (headers, source IP, body) and every scanned item | Route, request ID, status and error code only; tracebacks for unexpected errors |

`tests/test_baseline_equivalence.py` runs the original code and the current code over the same 17 requests, and fails on any difference not listed in this table.
