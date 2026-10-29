# Verification

Local verification and AWS verification are tracked separately. **Nothing in this repository has been deployed, and no step below authenticates to AWS.**

## Milestone 2: local end-to-end (verified)

Environment: Linux x86_64, Docker 29.9.2, Python 3.14.6, SAM CLI 1.170.0, `amazon/dynamodb-local:3.3.2`, `public.ecr.aws/lambda/python:3.14-x86_64`. Credentials were synthetic (`local`/`local`), with `~/.aws` hidden.

| Check | How | Result |
| --- | --- | --- |
| Full CRUD workflow over HTTP | `scripts/demo_requests.sh` → [evidence/local-http-run.txt](evidence/local-http-run.txt) | Create, read, list, update, read updated, delete, confirm deletion: all as expected |
| Integration suite (10 tests) | `make test-integration` → [evidence/integration-test-run.txt](evidence/integration-test-run.txt) | 10 passed |
| Repeatability | `make local-test` (start, test, tear down) twice more from a clean state | 10/10 passed both times; 0 containers left afterwards |
| Lambda really uses DynamoDB Local | An item written directly to DynamoDB Local is returned by `GET /items/{id}` | Pass |
| Lambda runs in Docker on the shared network | SAM log: `Invoking items_api.handler.lambda_handler (python3.14)`; `docker ps` shows the Lambda and DynamoDB containers on `items-local-net` | Confirmed |
| Database failure | The table is deleted, then `GET` and `PUT` are sent | The Lambda raised `ResourceNotFoundException` from DynamoDB Local's `Scan` and `PutItem` |
| Malformed JSON / bad price | `PUT` with invalid JSON, or `price: "abc"` | The Lambda raised `JSONDecodeError` / `InvalidOperation` (seen in the SAM log) |
| Missing item / missing field | `GET` of an unknown id; `PUT` without `name` | HTTP 400, same as the baseline |
| No real AWS endpoint contacted | `amazonaws.com` searched for in the SAM log; endpoint-guard unit tests | 0 matches; the guard rejects AWS, `execute-api` and private-IP URLs |
| Production endpoint unchanged | Unit tests inspect the boto3 client with `DYNAMODB_ENDPOINT_URL` unset or `''` | Uses `https://dynamodb.us-east-1.amazonaws.com` (no request is sent) |
| Logs keep only the route | SAM log shows `routeKey=...`, not the full event | Confirmed |
| Cleanup | `make local-down`, then `docker ps -a` and `docker network ls` | No containers or network left |
| Milestone 1 checks still pass | `make verify` | 17 unit tests passed; lint, validate and build OK |

### How the integration tests classify responses

| Class | Tests | What passes |
| --- | --- | --- |
| Correct application responses | CRUD workflow, seeded read, empty-table isolation, delete of a missing id | Exact status and body only |
| Expected error responses (legacy wording) | Missing item, missing `PUT` field | Exact `400` and the baseline's "Unsupported route" message |
| Known crash (legacy defect + emulator behavior) | Malformed JSON, non-numeric price, missing table | Only the two exact crash shapes: sam local's `200` with exactly `errorMessage`/`errorType`/`requestId`/`stackTrace` and the expected `errorType`, or API Gateway's `500 {"message":"Internal Server Error"}`. Each one raises a `LegacyUnhandledError` warning, so it shows in the run output; it's never counted as correct behavior. The test also checks that nothing was written. |
| Request never reaches the Lambda | `PATCH /items` | Exactly `403 Missing Authentication Token` (sam local) or `404 Not Found` (API Gateway) |
| Anything else | | Fails the test |

A deliberate check confirmed the crash assertion rejects a `200` that only claims an `errorType`, a success-looking `200`, a `502`, a `500` with another body, and a real crash with the wrong `errorType`.

**To strengthen in the error-handling milestone:** the three `*_crashes_function_legacy` tests become handled JSON `400` (malformed JSON, bad price) and `500`/`503` (database failure) with no stack trace, and the `LegacyUnhandledError` helper is removed. The two "Unsupported route" 400s become a `404` (missing item) and a `400` with a real message (missing field).

### Where the local emulator differs from API Gateway

Recorded during this milestone. The tests accept both behaviors.

| Situation | `sam local start-api` (observed) | API Gateway HTTP API (per AWS docs; **not verified here**) |
| --- | --- | --- |
| Lambda raises an unhandled error | **HTTP 200** with Lambda's error JSON, **including a stack trace** | HTTP 500 `{"message":"Internal Server Error"}` |
| Route not defined (e.g. `PATCH /items`) | HTTP 403 `{"message":"Missing Authentication Token"}` | HTTP 404 `{"message":"Not Found"}` |
| Throttling (5 req/s, burst 10) | Not applied | Applied at the stage |

## Milestone 1: static and unit checks (verified)

| Check | Result |
| --- | --- |
| Baseline copied unchanged (`sha256sum` against the exported package) | Identical |
| Refactor matches baseline: 17 events, moto | Pass; a deliberate one-character change made it fail as expected |
| Service unit tests | Pass |
| cfn-lint, `sam validate --lint`, `sam build` | Clean / valid / succeeded |
| Generated IAM (offline transform) | Role assumable only by `lambda.amazonaws.com`; 4 DynamoDB actions on the table ARN, plus `AWSLambdaBasicExecutionRole` |

## Not verified (needs a real AWS deployment)

- The stack creates successfully under the project's managed SCPs and service quotas.
- Real API Gateway → Lambda integration, including the 500 and 404 behaviors above.
- The scoped IAM policy is enough at runtime (no `AccessDenied`).
- Throttling, log retention, the `ApiEndpoint` output and the generated table name.
- Behavior differences between DynamoDB Local and the DynamoDB service (DynamoDB Local doesn't enforce IAM, throughput limits, or every validation rule).
- The key schema of the original console-created table (`id`, String) came from the tutorial, not from AWS.
- An arm64 host (Apple Silicon) wasn't tested. The function targets x86_64, so SAM runs it under emulation there, which works but is slower.

## Milestone 3: CI

See [ci.md](ci.md). Results of the GitHub-hosted run are recorded there once it has run.

## Planned

- Only with approval: deploy a test stack in the project's Region, run `scripts/demo_requests.sh` against `ApiEndpoint`, record the results here, then delete the stack.
