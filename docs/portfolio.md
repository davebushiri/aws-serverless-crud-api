# Portfolio materials

Ready-to-use text for the GitHub repository, a resume, interviews and LinkedIn. Every statement is limited to work that is in this repository or was verified as described in [verification.md](verification.md). The hardened v2 version has **not** been deployed to AWS; the original tutorial version was deployed by hand, and its GET and PUT routes were tested through API Gateway.

## A. GitHub repository description

> Serverless CRUD API on AWS (API Gateway HTTP API, Lambda/Python 3.14, DynamoDB) as AWS SAM infrastructure as code, with least-privilege IAM, a versioned error contract, Docker-based local testing (DynamoDB Local, SAM Local) and GitHub Actions CI with no cloud credentials.

Suggested topics: `aws`, `aws-sam`, `aws-lambda`, `api-gateway`, `dynamodb`, `serverless`, `python`, `infrastructure-as-code`, `github-actions`.

## B. Resume entry

**Serverless CRUD API on AWS**: personal project · Python, AWS SAM, Lambda, API Gateway, DynamoDB, Docker, GitHub Actions

- Built and tested a serverless REST-style API in AWS (API Gateway HTTP API, Lambda in Python, DynamoDB), then codified it as AWS SAM infrastructure as code. Replaced a broad managed policy with a least-privilege execution role (four DynamoDB actions on one table, logs on one log group only), enforced by automated template tests.
- Designed and implemented a versioned API error contract (400/404/405/413/500/503 JSON errors, schema validation, 8 KiB body limit, DynamoDB error classification with bounded retries) that keeps success responses backward compatible, verified against the original code by a compatibility test suite.
- Created a zero-cloud-cost verification pipeline: 79 unit tests and 19 end-to-end HTTP tests run against DynamoDB Local and SAM Local in Docker, and GitHub Actions CI on a clean runner with a read-only token, hash-locked dependencies, SHA-pinned actions and no AWS credentials.

Optional, if relevant to the role (for example AI Solutions Architect), and only if accurate in how you describe it: *"Directed an AI coding agent through five scoped milestones under explicit governance constraints (no cloud spend, no deployment without approval, evidence required for every claim), reviewing and verifying each change."*

## C. Two-minute explanation

**Problem.** I'd built the AWS tutorial CRUD API by hand in the console: API Gateway, a Python Lambda and a DynamoDB table. It worked, but it couldn't be reproduced or tested, it ran with a broad role, and bad requests crashed the function and could leak internal details.

**Architecture.** It's a standard serverless request path: an API Gateway HTTP API with four routes invokes one Lambda function, which reads and writes a DynamoDB table with a single `id` key. Everything is defined in one AWS SAM template: the API with a throttle, the function, an on-demand table, a dedicated log group with 14-day retention, and an explicit execution role.

**Implementation.** I split the handler into three layers. The handler deals with HTTP: routing, body limits, JSON parsing and turning errors into responses. The service holds validation and business rules. The repository is the only code that talks to DynamoDB, and it classifies DynamoDB failures.

**Decisions.** I kept every success response identical to the original so existing clients wouldn't break, and changed only errors: one JSON format with stable codes. For IAM, I found that SAM's default role attaches a managed policy allowing log writes on any resource, and an inline policy can't narrow that, so the template now defines its own role, scoped to one table and one log group.

**Reliability.** Expected problems get specific answers: 400 for bad input, 404 for missing items, 413 for oversized bodies. Unexpected faults get a generic 500 with the detail logged server-side only. DynamoDB throttling or connection failures get a 503. I bounded the boto3 timeouts and retries so a failing database returns a 503 inside the Lambda timeout instead of timing out.

**Testing.** Everything runs without AWS. Unit tests cover validation, error mapping, logging and the IAM policy. Integration tests send real HTTP requests through SAM Local to the Lambda runtime container and DynamoDB Local, including stopping the database to prove the 503 path. GitHub Actions runs all of it on a clean runner with no AWS credentials.

**Before production,** I'd add authentication, per-client rate limiting and budget and error alarms, replace the full-table Scan with pagination, and run a short deployment smoke test, because local emulation can't verify IAM, API Gateway behavior or real DynamoDB limits.

## D. Interview questions and answers

**1. Why API Gateway HTTP API instead of a REST API?**
It's what the tutorial used, and it's cheaper and lower-latency for a simple Lambda proxy. The tradeoff is that HTTP APIs lack request validation, API keys and usage plans, so validation lives in the Lambda (`service.parse_item`, `handler.parse_json_body`), and invalid requests still invoke the function. If I needed per-client quotas, I'd consider a REST API with usage plans, or WAF rate-based rules.

**2. How would you secure this before exposing it?**
It has no authentication, so it must not be public as-is. I'd add a JWT authorizer (Cognito or another OIDC provider) or IAM authorization, decide which callers may write and delete, add per-client throttling and a Budgets alarm, and keep the existing controls: strict validation, the 8 KiB limit, generic error bodies and no request data in logs. `docs/security.md` lists the open findings.

**3. Walk me through the IAM design.**
The function's role allows `GetItem`, `PutItem`, `DeleteItem` and `Scan` on the table's ARN, plus `CreateLogStream` and `PutLogEvents` on its own log group's streams. Nothing else. Originally SAM generated the role and attached `AWSLambdaBasicExecutionRole`, which allows log actions on `*`. Since IAM is a union of policies, I had to supply the role explicitly rather than add a narrower policy. A test expands the template offline and fails on any managed policy, wildcard resource or extra action. I haven't verified it in AWS yet; a deployment smoke test would confirm the logs arrive.

**4. Why DynamoDB, and what happens as the data grows?**
Access is by a single key, so `GetItem`/`PutItem`/`DeleteItem` fit perfectly, on-demand billing costs nothing when idle, and there's an official local emulator. The weak spot is `GET /items`, a single Scan: it returns at most 1 MB, and its cost grows with the table. I'd add pagination with `LastEvaluatedKey` and a page limit, and a GSI if a real query pattern appeared.

**5. How do you distinguish a 500 from a 503?**
The repository classifies DynamoDB errors. Throttling, DynamoDB 5xx, and connection or timeout errors are temporary, so they become `503 SERVICE_UNAVAILABLE`, which a client can retry. Anything else, such as a missing table or access denied, is a configuration or code fault that retrying won't fix, so the handler's catch-all returns `500 INTERNAL_ERROR` and logs the traceback. boto3 is limited to two attempts with 1 s connect and read timeouts, and the Lambda timeout is 6 s, so the 503 is always returned before Lambda would time out.

**6. How did you test this without AWS, and what can't that catch?**
Unit tests use an in-memory repository or moto. Integration tests run `sam local start-api`, which runs the handler in the official Lambda Python 3.14 container, against DynamoDB Local on a Docker network, and send real HTTP requests. One test stops the database container to check the 503. What it can't catch: IAM isn't enforced locally, SAM Local's routing and error responses differ from API Gateway (403 locally vs 404 per the API Gateway docs for unknown routes, and a crash shows up as HTTP 200 with a stack trace locally), throttling isn't emulated, and DynamoDB Local doesn't throttle.

**7. How did you change the API without breaking clients?**
I kept the original Lambda in `baseline/` and run it and the new code on the same 17 requests in moto. Every response must either match the original exactly or match a specific change listed in the test and in `docs/api-contract.md`. The five success responses are unchanged. The breaking changes for invalid input, such as rejecting `"19.99"` as a price or returning 404 when deleting a missing item, are documented in an ADR.

**8. What drives cost, and how did you control it?**
In AWS: Lambda invocations and duration, API Gateway requests, DynamoDB reads, writes and storage, and log ingestion. The template uses on-demand capacity, a stage throttle of 5 requests per second, 14-day log retention, a 128 MB function and bounded timeouts. During development the cost was zero: all testing ran locally and in CI with no AWS calls, and CI runs manually under a $0 stop-usage budget. The open risk is that an unauthenticated endpoint can still be used to write data and drive Scans, which is why authentication comes first.

## E. LinkedIn project description

**Serverless CRUD API on AWS (AWS SAM, Lambda, API Gateway, DynamoDB)**

I took the AWS console tutorial for a serverless CRUD API, which I first built and tested by hand in AWS, and turned it into a reproducible, tested project. The infrastructure is defined in AWS SAM, with a least-privilege execution role scoped to one DynamoDB table and one log group. The Python code is split into handler, service and repository layers, with a versioned API contract: consistent JSON errors, input validation and separate handling of client errors, unexpected faults and temporary database outages, while keeping existing success responses compatible. Everything runs locally in Docker with DynamoDB Local and SAM Local, covered by 79 unit tests and 19 end-to-end HTTP tests, and GitHub Actions repeats the full build and test on a clean runner without any AWS credentials. The repository documents the architecture decisions, a security review and the limits of local testing, including what still needs to be verified in a real deployment.
