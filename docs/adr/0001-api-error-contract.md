# ADR 0001: Explicit error contract (API v2)

- **Status:** Accepted (Milestone 4)
- **Context date:** 2026-10-29

## Context

The original tutorial handler (contract v1) let most bad requests crash the function. Through API Gateway that becomes an opaque `500`; through `sam local` it is an HTTP `200` carrying a full stack trace with AWS error details. Missing items returned `400 "Unsupported route"`, deleting a missing item returned `200`, any value was accepted for `id`, `price` and `name`, and the full request event (headers, source IP, body) was logged. Clients couldn't tell their own mistakes apart from server faults, and internal details could leak.

## Decision

1. **Keep every success response byte-for-byte the same** as v1 (including the list-wrapped item shapes), so existing clients keep working. Changing those shapes would be a separate, versioned decision.
2. **Errors use one JSON format,** `{"error": {"code", "message"}}`, with stable codes: `INVALID_JSON`, `VALIDATION_ERROR` (400), `ITEM_NOT_FOUND`/`ROUTE_NOT_FOUND` (404), `METHOD_NOT_ALLOWED` (405), `PAYLOAD_TOO_LARGE` (413), `INTERNAL_ERROR` (500) and `SERVICE_UNAVAILABLE` (503).
3. **Validate strictly** with a small hand-written schema in `service.py` (no new dependency), reject unknown fields, and cap bodies at 8 KiB.
4. **Classify DynamoDB failures in the repository:** throttling, DynamoDB 5xx, connection and timeout errors become `503` (retryable); everything else, including a missing table or an access error, is a `500` (configuration fault, not retryable). Missing items on delete are detected with a conditional delete.
5. **Bound the time spent on DynamoDB** (1 s connect, 1 s read, 2 attempts) and raise the Lambda timeout from 3 s to 6 s, so a failing dependency produces a `503` instead of a Lambda timeout.
6. **Catch everything else at the handler** and return a generic `500`. The traceback is logged; the request event, headers and body are not.
7. **Don't add a catch-all `$default` route.** Unknown paths stay with API Gateway's own `404`, so random scanning traffic doesn't start Lambda invocations. The handler still returns `404`/`405` in the v2 format if invoked directly.

## Consequences

- Clients get stable, documented error codes. No stack trace or AWS detail reaches a response (checked by the integration tests).
- **Breaking for invalid input that v1 accepted:** numeric strings for `price`, unknown fields, out-of-range values and unrestricted `id`s are now rejected; `DELETE` of a missing id is now `404`. These changes are listed in [api-contract.md](../api-contract.md) and checked against the original code by `tests/test_baseline_equivalence.py`.
- Platform responses for unknown routes (`404` in API Gateway, `403` in sam local) don't follow the v2 format.
- The longer Lambda timeout raises the worst-case billed duration of a failing request from 3 s to about 4 s (2 attempts × 2 s). Normal requests are unaffected.
- `ConditionExpression` on `DeleteItem` needs no extra IAM permission.

## Alternatives considered

- **Pydantic or jsonschema** for validation: clearer for big schemas, but a new runtime dependency to package for three fields.
- **Powertools for AWS Lambda** (routing, validation, structured logging): a good fit as the API grows; more than this milestone needs.
- **Returning `404` for a missing item while keeping `DELETE` idempotent (`204`/`200`):** reasonable, but the brief asked for `404` for missing resources, and a conditional delete makes it accurate.
