# Security review

Scope: the code, `template.yaml`, local tooling and CI workflow at Milestone 5. Method: code and template review, offline expansion of the SAM template, unit and integration tests. **Nothing was tested against AWS**, so IAM, API Gateway and CloudWatch behavior is reviewed from the template and AWS documentation, not observed.

> **This API must not be exposed publicly as-is.** It has no authentication or authorization: anyone who knows the URL could read, create, overwrite and delete every item. Before any deployment that is reachable for more than a short, supervised test, add an authorizer (for example a JWT authorizer backed by Amazon Cognito, or IAM authorization) and per-client rate limits.

## Summary of findings

| # | Area | Finding | Status |
| --- | --- | --- | --- |
| 1 | Authentication | No authorizer on any route | **Open**: blocks public exposure |
| 2 | IAM (logging) | SAM-attached `AWSLambdaBasicExecutionRole` allowed `logs:*` actions on `Resource: *` | **Fixed** in Milestone 5 ([ADR 0002](adr/0002-scoped-execution-role.md)); verified offline only |
| 3 | Error disclosure | v1 returned stack traces with AWS error details (through `sam local`), and an opaque 500 in AWS | **Fixed** in Milestone 4: generic JSON errors; tests fail on any leak |
| 4 | Logging | v1 logged the full event (headers, source IP, body) | **Fixed** in Milestone 1/4: route, request ID, status, error code only |
| 5 | Input validation | v1 accepted any field types, sizes and extra fields | **Fixed** in Milestone 4: strict schema, 8 KiB body limit |
| 6 | Throttling | One stage-wide limit (5 req/s, burst 10); no per-client limit | **Open**: acceptable for a demo only |
| 7 | Cost exposure | An open endpoint lets anyone write data and drive Scans and invocations | **Open**: bounded by the throttle, not by a budget alarm |
| 8 | Data protection | No backups (PITR off), `DeletionPolicy: Delete`; default AWS-owned encryption key | **Accepted** for synthetic demo data |
| 9 | Dependencies | No automated update or vulnerability alerts (Dependabot, pip-audit) | **Open**: low priority |

## IAM permissions

The function's execution role (`ItemsFunctionExecutionRole`, declared explicitly in `template.yaml`):

| Action | Resource |
| --- | --- |
| `dynamodb:GetItem`, `dynamodb:PutItem`, `dynamodb:DeleteItem`, `dynamodb:Scan` | The `ItemsTable` ARN only |
| `logs:CreateLogStream`, `logs:PutLogEvents` | `…:log-group:<ItemsFunctionLogGroup>:log-stream:*` only |

- **Trust policy:** `lambda.amazonaws.com` may assume the role (`sts:AssumeRole`). Nothing else.
- **No managed policies.** Before this milestone, SAM generated the role and attached `AWSLambdaBasicExecutionRole` (`logs:CreateLogGroup/CreateLogStream/PutLogEvents` on `*`). An inline policy can't narrow that, because IAM grants the union of attached policies, so the template now supplies the role itself. The offline expansion shows exactly one role, with no `ManagedPolicyArns`.
- **Not needed:** `logs:CreateLogGroup` (the group is created by the template), `Query`/`UpdateItem`/batch operations (not called), any network or KMS permissions.
- **API Gateway → Lambda:** SAM generates one `AWS::Lambda::Permission` per route for `apigateway.amazonaws.com`, with a `SourceArn` limited to this API and that route's method and path (any stage), e.g. `execute-api:…:<ItemsApi>/*/GET/items`.
- **Regression test:** `tests/test_template_iam.py` fails if a managed policy, a `Resource: "*"`, an extra action or a SAM-generated role appears.
- **Not verified:** whether these exact permissions are sufficient at runtime. DynamoDB Local and `sam local` don't enforce IAM.

## Authentication and authorization

None. The HTTP API has no authorizer, no API keys and no CORS configuration (browsers on other origins can't call it, but any non-browser client can). This is the main reason the project is a local-first demonstration and not a deployable public service.

## Input validation and request limits

Enforced in the Lambda (HTTP APIs have no request-schema validation):

- Body: JSON object, at most **8 KiB** after base64 decoding; `NaN`/`Infinity` and deeply nested JSON rejected (`400 INVALID_JSON`); larger bodies rejected with `413`.
- `id`: 1–64 characters from `A–Z a–z 0–9 . _ ~ -` (also for the `{id}` path parameter).
- `price`: JSON number, 0–1,000,000, at most 2 decimals; `name`: 1–200 characters, not only whitespace.
- Unknown fields rejected. Validation messages never echo user input.

Invalid requests still invoke the Lambda (and count toward cost) because validation runs inside it.

## Error handling and information disclosure

- Every response from the Lambda is an explicit proxy response with `{"error": {"code", "message"}}` for failures ([api-contract.md](api-contract.md)).
- Unexpected exceptions become `500 INTERNAL_ERROR` with a fixed message; DynamoDB outages become `503` with a fixed message. AWS error codes, table names and tracebacks stay in the function log.
- Tests: every integration response is checked; a crash payload (`errorType`/`stackTrace`) fails the test immediately, and error bodies are scanned for `Traceback`, `botocore`, `ResourceNotFound`, the table name, `dynamodb`, `/var/task` and `arn:aws`. A deliberate removal of the catch-all handler made the suite fail.
- Requests that never reach the Lambda (unknown routes) get API Gateway's own response, which contains no internal detail.

## Logging

- One line per request: route, request ID, status; failures add the error code and an internal detail (for example `DynamoDB EndpointConnectionError`).
- Unexpected exceptions are logged with a traceback (server-side only).
- **Never logged:** the event, headers (including `Authorization`), source IP, request body. A unit test sends a bearer token and a private value and checks that neither appears in the log.
- Retention: 14 days in a dedicated log group. No log encryption with a customer-managed key, no metric filters or alarms.

## Dependency management

- **Runtime:** no packaged dependencies; boto3 comes from the AWS-managed Python 3.14 runtime (`UpdateRuntimeOn: Auto` by default).
- **Dev and CI tools:** top-level pins in `requirements-dev.txt`, with all 90 packages hash-locked in `requirements-dev.lock` and installed with `--require-hashes`.
- **GitHub Actions:** pinned to full commit SHAs, releases at least about two weeks old; workflow linted with actionlint and zizmor.
- **Container images:** `amazon/dynamodb-local:3.3.2` and `public.ecr.aws/lambda/python:3.14-x86_64` are pinned by tag, not digest (local and CI only).
- **Gap:** no automated update or vulnerability alerts.

## API throttling

The `$default` stage limits the whole API to 5 requests per second with bursts of 10. This caps the request rate, not the total over time, and is shared by all clients: one client can use the entire allowance (denial of service for others). There are no per-client limits, usage plans or WAF rules.

## Cost and resource risks

- An open endpoint lets anyone invoke the Lambda (including with invalid requests), write items (storage grows without limit) and trigger `GET /items` Scans, whose cost grows with the table size.
- The throttle bounds the rate of requests; a failing request is bounded to a few seconds of Lambda time (6 s timeout, about 4 s worst case for the DynamoDB calls).
- No AWS Budgets alarm or CloudWatch alarm is defined in the template.
- Development and CI make **no AWS calls**, so they create no AWS cost. GitHub Actions minutes are covered by the account's included minutes and a $0 stop-usage budget set by the owner.

## Data handling

- Use **synthetic data only**. The schema has no personal-data fields; nothing prevents a client from putting personal data in `name`.
- At rest: DynamoDB default encryption (AWS-owned key). In transit: HTTPS to API Gateway (AWS-managed endpoint).
- No backups (point-in-time recovery off, which costs extra), and deleting the stack deletes the table (`DeletionPolicy: Delete`).
- `price` is returned as a float, so it isn't suitable for exact monetary values.
- Local and CI runs use in-memory DynamoDB Local; data disappears when the container stops.

## Before any real deployment

1. Add an authorizer (JWT/Cognito or IAM) and decide who may write and delete.
2. Add per-client limits (usage plans on a REST API, or WAF rate-based rules) and an AWS Budgets alarm.
3. Deploy to a test stack in the project's Region, run `scripts/demo_requests.sh` against it, and confirm that logs reach the dedicated log group with the scoped role.
4. Turn on point-in-time recovery if the data matters, and consider `DeletionPolicy: Retain`.
