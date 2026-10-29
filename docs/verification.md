# Verification

Local verification and AWS verification are tracked separately. **Nothing in this repository has been deployed by these steps.**

## Done locally (Milestone 1)

Environment: Linux, Python 3.14.6, SAM CLI 1.170.0, cfn-lint 1.58.0, with AWS config and credentials hidden (`boto3.Session().get_credentials()` returned `None`).

| Check | Command | Result |
| --- | --- | --- |
| Baseline copied unchanged | `sha256sum` against the exported Lambda package | Identical hash |
| Refactor matches baseline (17 events: success, edge and error cases) | `make test` | Pass |
| Baseline behaviors pinned (400 on missing item, 500 on bad JSON, etc.) | `make test` | Pass |
| `TABLE_NAME` environment configuration | `make test` | Pass |
| Service unit tests (no AWS, no mocks) | `make test` | 6 pass |
| Equivalence test can fail | Changed one character in a response, ran the test | Failed at step 1 as expected; change reverted |
| Template lint | `make lint` (cfn-lint) | No errors or warnings |
| SAM validation | `make validate` (`sam validate --lint`) | Valid SAM template |
| Build | `make build` (`sam build`) | Build succeeded; artifact contains only `items_api/` |
| Built artifact runs | Imported the handler from `.aws-sam/build`, PUT then GET against moto | 200 responses with the expected body |
| Generated IAM | Offline SAM transform with a stubbed managed-policy lookup | Role assumable only by `lambda.amazonaws.com`; 4 DynamoDB actions on the table ARN, plus `AWSLambdaBasicExecutionRole` |

## Not verified

These need a real deployment, which hasn't happened:

- The stack actually creates successfully (CloudFormation can still reject something that passes linting, such as service quotas or the project's managed SCPs).
- The Python 3.14 runtime and the HTTP API proxy integration work end to end with the real event format.
- The scoped IAM policy is enough at runtime (no `AccessDenied`).
- Throttling, log retention and the `ApiEndpoint` output behave as configured.
- The key schema of the original console-created table (`id`, String) was taken from the tutorial, not read from AWS.
- Moto is a simulation; DynamoDB Local or real DynamoDB may differ in edge cases.

## Planned

- Milestone 2: integration tests against DynamoDB Local; `sam local invoke -e events/...` with `DYNAMODB_ENDPOINT_URL`.
- Milestone 3: GitHub Actions running `make verify` without AWS credentials.
- Only with approval: deploy to a test stack, run smoke tests against `ApiEndpoint` for each route, record the results here, then delete the stack.
