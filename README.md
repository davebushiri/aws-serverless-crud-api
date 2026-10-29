# Items CRUD API (AWS SAM)

A serverless CRUD API for items: **Amazon API Gateway HTTP API → AWS Lambda (Python 3.14) → Amazon DynamoDB**, defined as infrastructure as code with AWS SAM.

It started as the AWS tutorial "Build a CRUD API with Lambda and DynamoDB", which was built by hand in the console. This repository makes it reproducible from code, separates the handler from the business logic, scopes IAM to least privilege, and verifies the refactor against the original code.

> **Status:** Milestone 2. The full CRUD workflow runs end to end on your machine: HTTP → `sam local start-api` → Lambda container → DynamoDB Local. Nothing has been deployed or tested in AWS. See [docs/verification.md](docs/verification.md).

## API

| Route | Behavior | Response body |
| --- | --- | --- |
| `PUT /items` | Create or replace an item. Body: `{"id": "123", "price": 12.5, "name": "x"}` | `"Put item 123"` |
| `GET /items/{id}` | Read one item | `[{"price": 12.5, "id": "123", "name": "x"}]` |
| `GET /items` | List items (one Scan page) | `[[{...}], [{...}]]` |
| `DELETE /items/{id}` | Delete an item | `"Deleted item 123"` |

Response shapes deliberately match the original tutorial code, quirks included. They're listed in [docs/architecture.md](docs/architecture.md#known-baseline-behaviors).

## Project layout

```
template.yaml            SAM template: HTTP API, Lambda, DynamoDB, scoped IAM, log group
samconfig.toml           Build and validate settings (no deploy settings)
src/items_api/
  handler.py             Lambda entry point: event parsing, routing, HTTP responses
  service.py             Business logic, independent of Lambda and API Gateway
  repository.py          DynamoDB access; table from TABLE_NAME env var
baseline/                The original tutorial Lambda, unchanged (reference only, not deployed)
tests/                   Unit tests (moto, no Docker) and tests/integration/ (local HTTP API)
local/env.json           Environment for the local Lambda: table name and DynamoDB Local URL
scripts/                 local.sh (start/stop the stack), local_table.py, demo_requests.sh
events/                  Sample HTTP API events for `sam local invoke`
docs/                    Architecture, verification results, recorded evidence
Makefile                 Local-only targets
```

## Run it locally

No AWS account or credentials are needed for anything below.

**Requirements:** Python 3.14, [uv](https://docs.astral.sh/uv/), `make`, `curl`, and Docker (only for the local stack).

```bash
git clone https://github.com/davebushiri/aws-serverless-crud-api.git
cd aws-serverless-crud-api
make install     # .venv with SAM CLI, cfn-lint, pytest, moto
make verify      # unit tests + cfn-lint + sam validate --lint + sam build (no Docker)
```

### Local HTTP API

```bash
make local-up            # DynamoDB Local + sam local start-api on http://127.0.0.1:3000
curl -X PUT http://127.0.0.1:3000/items -d '{"id": "1", "price": 9.5, "name": "test"}'
curl http://127.0.0.1:3000/items/1
make test-integration    # end-to-end tests against the running stack
scripts/demo_requests.sh # prints the full CRUD walkthrough
make local-down          # stops SAM, removes the containers and the network
```

Or run everything in one go with `make local-test` (start, test, always tear down).

```
curl ─▶ sam local start-api :3000 ─▶ Lambda container (python3.14) ─▶ DynamoDB Local :8000 (in-memory)
         (on the host)                 └────────── Docker network items-local-net ──────────┘
```

- The Lambda container reaches DynamoDB Local by container name (`http://items-dynamodb-local:8000`, set in `local/env.json`). Tests on the host use `127.0.0.1:8000`; both ports are bound to localhost only.
- All local commands run with synthetic credentials (`local`/`local`) and with `~/.aws` hidden. The test helpers refuse any endpoint that isn't `localhost` or `127.0.0.1`.
- DynamoDB Local runs in memory, and every integration test recreates the table, so runs are isolated and repeatable.
- Images: `amazon/dynamodb-local:3.3.2` (Docker Hub) and `public.ecr.aws/lambda/python:3.14-x86_64` (the public ECR gallery; an anonymous pull, no AWS account involved).

## Configuration

| Variable | Required | Purpose |
| --- | --- | --- |
| `TABLE_NAME` | yes | DynamoDB table. In AWS, the template sets it to the generated table name; locally it's `items-local`. |
| `DYNAMODB_ENDPOINT_URL` | no | Points boto3 at DynamoDB Local. Empty in AWS, so boto3 uses its normal endpoint. |

## Deploying

Not part of Milestone 1. Deployment needs an explicit decision and AWS credentials. It would be `sam deploy --guided`, followed by smoke tests against the output `ApiEndpoint`. Before deploying, read [docs/architecture.md](docs/architecture.md#limitations): the API has no authentication.

## Roadmap

1. Milestone 1: SAM template, refactor, baseline-equivalence tests, local build.
2. **Milestone 2 (this):** DynamoDB Local and `sam local start-api` with end-to-end integration tests.
3. Next: GitHub Actions running `make verify` and `make local-test` on every push. It needs no AWS credentials.
4. Later: input validation and proper 404s (an API change), pagination, authentication.
