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
| **x86_64, 128 MB, 3 s timeout** | Same settings as the deployed function | arm64 is about 20% cheaper per GB-second, a possible later change |
| **No runtime dependencies** | boto3 is included in the Lambda Python runtime | Pinning boto3 in the package: a fixed version, but a larger package |

## Refactor summary

Behavior compared with `baseline/lambda_function.py` and kept the same:

- The same routes, status codes, headers and response bodies, including the error cases.
- The table name now comes from `TABLE_NAME` instead of being hard-coded.
- Removed: the unused `client` and `tableName` globals, and the leftover Node.js `index.mjs` from the exported package.
- **Changed on purpose (logs only):** the baseline printed the whole event, including request headers and source IP, plus every scanned item. The new handler logs only the `routeKey`. Responses are unaffected.

`tests/test_baseline_equivalence.py` sends the same 17 events to both versions and requires identical results.

## Known baseline behaviors

Kept for compatibility. Changing them changes the API, so they're planned as a separate milestone:

- `GET /items/{id}` returns a one-element **list**, and `GET /items` returns a list of one-element lists.
- A missing item returns **400** `"Unsupported route: GET /items/{id}"`, not 404.
- Missing fields in a `PUT` body return 400 with the same "Unsupported route" message.
- Invalid JSON, a non-numeric `price` or a non-string `id` raise an unhandled error, which API Gateway returns as **500**.
- `DELETE` of an id that doesn't exist returns 200.
- An unknown route reaching the function returns 200 `{}`. API Gateway only forwards the four defined routes, so this can't happen through the API.
- `price` is stored as a DynamoDB number and returned as a float, so it isn't safe for money.

## Limitations

- **No authentication or authorization.** Anyone with the URL can read, write and delete. Acceptable for a short-lived demo only; add a JWT authorizer (Cognito) or IAM auth before leaving it deployed.
- **`GET /items` is a single Scan:** at most 1 MB, no pagination, and cost grows with the table size.
- **Logging policy is broad:** SAM's `AWSLambdaBasicExecutionRole` allows creating log streams on any log group (`Resource: *`). A custom role could scope it to this function's log group.
- **No point-in-time recovery or backups**, which would cost extra. `DeletionPolicy: Delete` means deleting the stack deletes the data.
- **No API access logs or alarms** yet.
- **Single Region, single stage.** No custom domain.

## Dependencies

| Tool | Used for | Version tested |
| --- | --- | --- |
| Python | Runtime and tests | 3.14.6 |
| AWS SAM CLI | `validate`, `build` | 1.170.0 |
| cfn-lint | Template linting | 1.58.0 |
| pytest | Tests | 9.2.0 |
| moto | In-memory DynamoDB for tests | 5.2.5 |
| boto3 | AWS SDK (supplied by the Lambda runtime) | 1.43.108 locally |
