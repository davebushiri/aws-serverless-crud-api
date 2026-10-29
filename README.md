# Items CRUD API (AWS SAM)

A serverless CRUD API for items: **Amazon API Gateway HTTP API → AWS Lambda (Python 3.14) → Amazon DynamoDB**, defined as infrastructure as code with AWS SAM.

It started as the AWS tutorial "Build a CRUD API with Lambda and DynamoDB", which was built by hand in the console. This repository makes it reproducible from code, separates the handler from the business logic, scopes IAM to least privilege, and verifies the refactor against the original code.

> **Status:** Milestone 1. Verified locally only. The SAM template has **not** been deployed or tested in AWS. See [docs/verification.md](docs/verification.md).

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
tests/                   pytest: baseline equivalence (moto) and service unit tests
events/                  Sample HTTP API events for `sam local invoke`
docs/                    Architecture decisions and verification evidence
Makefile                 Local-only targets: install, test, lint, validate, build, verify
```

## Run it locally

Requirements: Python 3.14, [uv](https://docs.astral.sh/uv/) and `make`. Docker is not needed for these steps. No AWS account or credentials are needed.

```bash
make install   # creates .venv with SAM CLI, cfn-lint, pytest, moto
make verify    # tests + cfn-lint + sam validate --lint + sam build
```

Run steps individually with `make test`, `make lint`, `make validate` or `make build`. Every target runs with AWS config and credentials hidden, so nothing can reach an AWS account. Tests use [moto](https://github.com/getmoto/moto), an in-memory DynamoDB.

## Configuration

| Variable | Required | Purpose |
| --- | --- | --- |
| `TABLE_NAME` | yes | DynamoDB table. In AWS, the template sets it to the generated table name. |
| `DYNAMODB_ENDPOINT_URL` | no | Points boto3 at DynamoDB Local (planned for Milestone 2). |

## Deploying

Not part of Milestone 1. Deployment needs an explicit decision and AWS credentials. It would be `sam deploy --guided`, followed by smoke tests against the output `ApiEndpoint`. Before deploying, read [docs/architecture.md](docs/architecture.md#limitations): the API has no authentication.

## Roadmap

1. **Milestone 1 (this):** SAM template, refactor, baseline-equivalence tests, local build.
2. Milestone 2: DynamoDB Local integration tests and `sam local invoke` with the files in `events/`.
3. Milestone 3: GitHub Actions running `make verify` on every push. It needs no AWS credentials.
4. Later: input validation and proper 404s (an API change), pagination, authentication.
