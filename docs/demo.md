# Technical demo (2–3 minutes)

A self-contained walkthrough for a recorded video or a live interview. It runs entirely on your machine with synthetic data; **no AWS account, credentials or AWS calls are involved.** No video has been recorded yet; this is the plan and script.

The expected outputs below were captured from a real run of these exact commands.

## Before recording

```bash
make install       # once: .venv with the locked tools
make local-up      # warm-up run: pulls the two Docker images
make local-down
```

Use a terminal with a large font. Open these files in an editor, in tabs: `template.yaml`, `docs/architecture.md` (Mermaid preview) and `src/items_api/handler.py`. Open the [CI run page](https://github.com/davebushiri/aws-serverless-crud-api/actions/runs/40828145799) in a browser.

## Run of show

| Time | Show | Say (short version) |
| --- | --- | --- |
| 0:00 | `docs/architecture.md` diagram | Problem, architecture, local-first approach |
| 0:20 | Step 1: `make local-up` | Real Lambda runtime and DynamoDB engine, in Docker |
| 0:40 | Steps 2–5: CRUD | Same request flow as API Gateway → Lambda → DynamoDB |
| 1:15 | Steps 6–7: errors | Contract v2: explicit, safe error responses |
| 1:35 | Step 8: tests | 79 unit and 19 HTTP integration tests |
| 2:00 | Step 9: `template.yaml` role | Infrastructure as code, least-privilege IAM |
| 2:20 | Step 10: CI run page | Independent evidence on a clean runner |
| 2:35 | Step 11: `make local-down` | Clean teardown; limitations and next steps |

## Steps, commands and expected output

Set the API address once:

```bash
API=http://127.0.0.1:3000
```

**1. Start the application locally** (about 15 s with cached images)

```bash
make local-up
```

Expected: the steps print, ending with `==> Ready: http://127.0.0.1:3000/items`. This starts DynamoDB Local and `sam local start-api` on one Docker network, and creates an empty table.

**2. Create an item**

```bash
curl -s -X PUT $API/items -H 'Content-Type: application/json' \
  -d '{"id": "demo-1", "price": 19.99, "name": "Widget"}' -w '\nHTTP %{http_code}\n'
```

```
"Put item demo-1"
HTTP 200
```

**3. Retrieve the item**

```bash
curl -s $API/items/demo-1 -w '\nHTTP %{http_code}\n'
```

```
[{"price": 19.99, "id": "demo-1", "name": "Widget"}]
HTTP 200
```

**4. Update the item, then list all items**

```bash
curl -s -X PUT $API/items -H 'Content-Type: application/json' \
  -d '{"id": "demo-1", "price": 24.50, "name": "Widget Pro"}' -w '\nHTTP %{http_code}\n'
curl -s $API/items -w '\nHTTP %{http_code}\n'
```

```
"Put item demo-1"
HTTP 200
[[{"price": 24.5, "id": "demo-1", "name": "Widget Pro"}]]
HTTP 200
```

**5. Delete the item**

```bash
curl -s -X DELETE $API/items/demo-1 -w '\nHTTP %{http_code}\n'
```

```
"Deleted item demo-1"
HTTP 200
```

**6. Validation error** (price sent as a string)

```bash
curl -s -X PUT $API/items -H 'Content-Type: application/json' \
  -d '{"id": "demo-2", "price": "abc", "name": "Widget"}' -w '\nHTTP %{http_code}\n'
```

```
{"error": {"code": "VALIDATION_ERROR", "message": "'price' must be a number."}}
HTTP 400
```

**7. Missing resource** (the item deleted in step 5)

```bash
curl -s $API/items/demo-1 -w '\nHTTP %{http_code}\n'
```

```
{"error": {"code": "ITEM_NOT_FOUND", "message": "Item not found."}}
HTTP 404
```

**8. Run the automated tests** (about 15 s)

```bash
make test
make test-integration
```

```
79 passed, 19 deselected
19 passed, 79 deselected
```

The first is the unit suite (no Docker). The second sends real HTTP requests to the running stack, including a test that stops the database container and expects a `503`, then restarts it.

**9. Review the SAM template and IAM controls**

Show `template.yaml`, from `ItemsFunctionExecutionRole:` down to the function's `Role:` line. Point out:

- four DynamoDB actions on this table's ARN only;
- `CreateLogStream`/`PutLogEvents` on this function's log group only;
- no managed policy, enforced by `tests/test_template_iam.py`;
- the API stage throttle (5 req/s, burst 10).

**10. Show CI**

In the browser, open [run 40828145799](https://github.com/davebushiri/aws-serverless-crud-api/actions/runs/40828145799). Show the green steps, the "Test results" summary table and the "confirm no AWS credentials" step.

**11. Clean up**

```bash
make local-down
docker ps
```

Expected: `Stopping sam local start-api`, `Removing items-dynamodb-local and network items-local-net`, then an empty `docker ps` list.

## Speaking script (about 2.5 minutes)

> This is a serverless CRUD API on AWS: API Gateway, Lambda in Python, and DynamoDB, defined with AWS SAM. It started as the AWS console tutorial, which I deployed and tested by hand. I turned it into a reproducible, tested project, and everything you'll see runs locally with no AWS account and no cloud cost.
>
> *(make local-up)* This starts DynamoDB Local and SAM's local API in Docker. The Lambda runs in the official Python 3.14 Lambda runtime image and talks to a real DynamoDB engine over a private Docker network, with fake credentials only.
>
> *(steps 2–5)* Create, read, update, list and delete. These success responses are byte-for-byte the same as the original tutorial code; I kept them compatible and test that against the original.
>
> *(steps 6–7)* What I changed is error handling. The original crashed on bad input and, locally, even returned a stack trace. Now there's one JSON error format with stable codes: 400 for invalid input, 404 for missing items, 500 for unexpected faults and 503 when DynamoDB is unavailable. Nothing internal leaks, and the tests check for that.
>
> *(make test, make test-integration)* 79 unit tests cover validation, error classification and safe logging. 19 integration tests go over HTTP through the local stack, including a test that stops the database and expects a clean 503.
>
> *(template.yaml)* The infrastructure is in one SAM template. The Lambda's role allows exactly four DynamoDB actions on this table and log writes to its own log group. I replaced SAM's default role because its managed policy allowed logging on any resource, and a test now enforces that.
>
> *(CI page)* GitHub Actions repeats all of this on a clean runner, with a read-only token and no AWS credentials. Here's the passing run.
>
> *(make local-down)* Everything is torn down. To be clear about limits: the hardened version hasn't been redeployed to AWS, so real IAM and API Gateway behavior is unverified, and there's no authentication. Before any real deployment I'd add an authorizer, per-client rate limits and a budget alarm, then run a short smoke test in AWS.

## If something goes wrong on camera

- `Port 3000 already in use`: run `make local-down`, or `API_PORT=3001 make local-up` and set `API=http://127.0.0.1:3001`.
- `Docker is not running.`: start Docker Desktop (or the Docker daemon) and rerun `make local-up`.
- First run is slow: the Docker images are being downloaded; do the warm-up run before recording.
