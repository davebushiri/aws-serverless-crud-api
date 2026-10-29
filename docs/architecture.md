# Architecture

```
Client ──HTTPS──▶ API Gateway HTTP API ($default stage, throttled)
                    │  4 routes, Lambda proxy integration (payload v2.0)
                    ▼
                  AWS Lambda  items_api.handler.lambda_handler (Python 3.14, 128 MB, 3 s)
                    │  handler.py → service.py → repository.py
                    ▼
                  Amazon DynamoDB  on-demand table, partition key id (String)
```

### Local development stack

```
host:   curl / pytest ──▶ sam local start-api 127.0.0.1:3000
                                │ invokes
docker network items-local-net: Lambda container (public.ecr.aws/lambda/python:3.14)
                                │ DYNAMODB_ENDPOINT_URL=http://items-dynamodb-local:8000
                                ▼
                          items-dynamodb-local (amazon/dynamodb-local:3.3.2, -inMemory -sharedDb)
host:   tests / table setup ──▶ 127.0.0.1:8000 (published to localhost only)
```

`-sharedDb` makes DynamoDB Local ignore the credentials and Region in a request, so the Lambda container and the host tests see the same table. `--warm-containers EAGER` keeps one Lambda container running for the whole session instead of starting one per request.

## Decisions

| Decision | Why | Alternative considered |
| --- | --- | --- |
| **HTTP API** (API Gateway v2) | Matches the tutorial; lower cost and latency than REST API | REST API: adds usage plans, API keys and request validation that aren't needed yet |
| **AWS SAM** | Serverless shorthand on top of CloudFormation; local build and invoke | CDK: more power, but adds a Node toolchain; plain CloudFormation: much more verbose |
| **DynamoDB on-demand** | No capacity planning; costs nothing when idle | Provisioned capacity: cheaper only at steady load |
| **Inline least-privilege IAM** | Grants only `GetItem`, `PutItem`, `DeleteItem` and `Scan` on this table | `DynamoDBCrudPolicy` also grants `Query`, `UpdateItem` and the batch operations |
| **Generated table name, passed as `TABLE_NAME`** | No hard-coded names; several stacks can coexist | Fixed `TableName`: blocks a second deployment and replacement updates |
| **Handler / service / repository split** | Business logic is testable without Lambda events or AWS | Single file: simpler, but tests would have to build Lambda events and mock boto3 |
| **API throttling** (5 req/s, burst 10) | Limits cost if the public endpoint is abused | WAF: per-IP rules, but it costs extra |
| **14-day log retention**, explicit log group | Logs don't build up forever; the group is deleted with the stack | Default: logs kept forever, group left behind |
| **x86_64, 128 MB, 6 s timeout** | Same as the deployed function, except the timeout (3 s → 6 s, so a failing DynamoDB call returns a 503; see ADR 0001) | arm64 is about 20% cheaper per GB-second, a possible later change |
| **No runtime dependencies** | boto3 is included in the Lambda Python runtime | Pinning boto3 in the package: a fixed version, but a larger package |
| **DynamoDB Local + `sam local start-api`** for integration tests | Runs the real handler in the real Lambda runtime image against a real DynamoDB engine, all for free | LocalStack: emulates API Gateway too, but it's a larger dependency and some features are paid; moto alone doesn't exercise HTTP or the container |
| **`DYNAMODB_ENDPOINT_URL` declared empty in the template** | `sam local --env-vars` can only override variables the template declares; an empty value keeps boto3's normal endpoint in AWS | A separate local template: two templates that can drift apart |

## Refactor summary

Behavior compared with `baseline/lambda_function.py` and kept the same:

- The same routes, status codes, headers and response bodies, including the error cases.
- The table name now comes from `TABLE_NAME` instead of being hard-coded.
- Removed: the unused `client` and `tableName` globals, and the leftover Node.js `index.mjs` from the exported package.
- **Changed on purpose (logs only):** the baseline printed the whole event, including request headers and source IP, plus every scanned item. The new handler logs only the `routeKey`. Responses are unaffected.

`tests/test_baseline_equivalence.py` sends the same 17 events to both versions and requires identical results.

## API contract

Success responses keep the original shapes; errors follow contract v2. See [api-contract.md](api-contract.md) for the v1 → v2 comparison and [adr/0001-api-error-contract.md](adr/0001-api-error-contract.md) for the decision.

Error handling by layer:

| Layer | Responsibility |
| --- | --- |
| `handler.py` | Routing, request-body limits and JSON parsing, mapping errors to HTTP responses, the catch-all `500`, safe logging |
| `service.py` | Item schema validation, not-found rules, success response shapes |
| `repository.py` | DynamoDB calls with bounded timeouts and retries; temporary failures → `503`, conditional delete → `404`, everything else propagates (`500`) |
| `errors.py` | Error classes, each with a status, a stable code and a safe default message |

## Limitations

- **No authentication or authorization.** Anyone with the URL can read, write and delete. Acceptable for a short-lived demo only; add a JWT authorizer (Cognito) or IAM auth before leaving it deployed.
- **`GET /items` is a single Scan:** at most 1 MB, no pagination, and cost grows with the table size.
- **Logging policy is broad:** SAM's `AWSLambdaBasicExecutionRole` allows creating log streams on any log group (`Resource: *`). A custom role could scope it to this function's log group.
- **No point-in-time recovery or backups**, which would cost extra. `DeletionPolicy: Delete` means deleting the stack deletes the data.
- **No API access logs or alarms** yet.
- **No rate limiting per client:** only the stage-wide throttle (5 req/s, burst 10). One client can use up the whole budget.
- **`price` is stored as a DynamoDB number but returned as a float,** so it isn't safe for exact money arithmetic.
- **Validation is in application code:** API Gateway HTTP APIs have no request-schema validation, so invalid requests still invoke (and bill) the Lambda.
- **Single Region, single stage.** No custom domain.

## Dependencies

| Tool | Used for | Version tested |
| --- | --- | --- |
| Docker | DynamoDB Local and the local Lambda runtime | 29.9.2 |
| DynamoDB Local | Local database (`amazon/dynamodb-local`) | 3.3.2 |
| Python | Runtime and tests | 3.14.6 |
| AWS SAM CLI | `validate`, `build` | 1.170.0 |
| cfn-lint | Template linting | 1.58.0 |
| pytest | Tests | 9.2.0 |
| moto | In-memory DynamoDB for tests | 5.2.5 |
| boto3 | AWS SDK (supplied by the Lambda runtime) | 1.43.108 locally |
