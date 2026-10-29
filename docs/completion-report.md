# Completion report

Project closure for the Serverless Items CRUD API portfolio project (Milestones 1–5).

## 1. Original objective

Turn the hand-built AWS console tutorial (API Gateway HTTP API → Lambda in Python → DynamoDB) into a reproducible, tested, documented engineering artifact, under a strict **zero additional AWS spend** rule: no deployments, no authenticated AWS calls and no paid services during development.

## 2. Work completed

| Milestone | Delivered |
| --- | --- |
| 1. Infrastructure as code | SAM template (HTTP API, Lambda, on-demand DynamoDB, log group, scoped DynamoDB permissions); handler/service/repository split; table name from `TABLE_NAME`; original Lambda kept in `baseline/`, with tests proving the refactor matched it |
| 2. Local integration | DynamoDB Local and `sam local start-api` on a Docker network; `make local-up`/`local-test`/`local-down`; end-to-end HTTP tests; localhost-only guards and synthetic credentials |
| 3. CI | GitHub Actions workflow (manual trigger, read-only token, SHA-pinned actions, hash-locked tools, no AWS credentials); stricter crash assertions; two cleanup and install bugs fixed |
| 4. API reliability | Contract v2: consistent JSON errors (400/404/405/413/500/503), schema validation, 8 KiB body limit, DynamoDB error classification with bounded timeouts, safe logging; success responses unchanged; compatibility test against the original; [ADR 0001](adr/0001-api-error-contract.md) |
| 5. Presentation and closure | Explicit least-privilege execution role replacing SAM's default managed policy ([ADR 0002](adr/0002-scoped-execution-role.md)) with regression tests; employer-facing README; architecture diagrams; security review; demo plan; portfolio materials; this report |

## 3. Verified functionality

Verified locally and on a GitHub-hosted runner, against DynamoDB Local and the official Lambda Python 3.14 runtime container:

- Create, read, list, update and delete, with responses identical to the original tutorial code.
- `400` for malformed JSON and invalid items, `404` for missing items, `413` for oversized bodies, a generic `500` for a missing table, and `503` with the database stopped, followed by recovery.
- No stack traces or internal details in any error response.
- No request headers or bodies in logs.
- IAM: the expanded template contains one role, with no managed policies and six scoped action/resource pairs.

The original tutorial version (before this project) was deployed by hand, and its GET and PUT routes were tested through API Gateway. **The v2 code has not been deployed.**

## 4. Automated test results

| Suite | Count | Result |
| --- | --- | --- |
| Unit (`make test`) | 79 | All pass |
| Integration over HTTP (`make local-test`) | 19 | All pass |
| Template (`make lint validate build`) | | cfn-lint clean, valid SAM template, build succeeded |

Counts grew from 17 unit / 10 integration (Milestone 2) to 77 / 19 (Milestone 4) and 79 / 19 (Milestone 5: two IAM template tests). No tests were removed to make a run pass. The Milestone 3 tests that accepted legacy crash payloads were replaced in Milestone 4 by exact error assertions, and any crash payload now fails a test.

## 5. Architectural decisions

Serverless with an HTTP API; DynamoDB on-demand with single-key access; AWS SAM; three code layers; success responses kept backward compatible while errors follow a versioned contract; temporary DynamoDB failures return 503 and other faults a generic 500; an explicit scoped execution role; local-first testing with emulators. Rationale and tradeoffs: [architecture.md](architecture.md#key-decisions) and [adr/](adr/).

## 6. Security limitations

No authentication or authorization (the main blocker for any public deployment); only a stage-wide throttle; no budget or error alarms; no backups; prices returned as floats; no automated dependency alerts; IAM sufficiency and API Gateway behavior not verified in AWS. Details: [security.md](security.md).

## 7. Cost

- **Development and CI:** no AWS calls, so no AWS cost. CI runs manually on a standard GitHub-hosted runner (about 75 s per run), covered by included Actions minutes under a $0 stop-usage budget set by the owner.
- **If deployed:** pay-per-request API Gateway, Lambda, DynamoDB on-demand and log ingestion. Bounded by the stage throttle, short timeouts and 14-day log retention, but not by authentication or a budget alarm.

## 8. Reproduction

```bash
git clone https://github.com/davebushiri/aws-serverless-crud-api.git
cd aws-serverless-crud-api
make install && make verify && make local-test
```

Needs Python 3.14, uv, make, curl and Docker. No AWS account. Walkthrough: [demo.md](demo.md).

## 9. Portfolio artifacts

[README](../README.md) · [architecture](architecture.md) · [API contract](api-contract.md) · [security review](security.md) · [ADRs](adr/) · [verification](verification.md) · [CI](ci.md) · [demo plan and script](demo.md) · [resume, interview and LinkedIn text](portfolio.md) · [recorded evidence](evidence/)

## 10. Final commit and CI

The final commit is the head of `main` in the GitHub repository. Code changes were last verified by GitHub Actions on the Milestone 5 commit; see the [CI runs](https://github.com/davebushiri/aws-serverless-crud-api/actions/workflows/ci.yml) (each run shows its commit). Earlier verified runs: [40825291736](https://github.com/davebushiri/aws-serverless-crud-api/actions/runs/40825291736) (Milestone 3), [40828145799](https://github.com/davebushiri/aws-serverless-crud-api/actions/runs/40828145799) (Milestone 4).

## 11. Outstanding issues

None blocking the portfolio. The known gaps are deliberate scope limits, documented above: no authentication; no AWS deployment of v2 (so IAM and API Gateway behavior are unverified); the full-table Scan; CI triggers manual only (pending the owner's decision).

## Portfolio completion checklist

- [x] Architecture understandable from the README and the diagrams
- [x] Infrastructure defined in `template.yaml`; validated, linted and built offline
- [x] Least-privilege IAM, enforced by tests
- [x] Technical decisions recorded (architecture page, two ADRs)
- [x] Reproducible locally with three commands, without AWS
- [x] Unit and end-to-end HTTP tests passing
- [x] Independent CI evidence on a clean runner
- [x] Security limits documented, including "not for public exposure without auth"
- [x] Verified vs. unverified behavior clearly separated
- [x] Demo plan, speaking script and interview material prepared
- [x] No secrets, account identifiers or live endpoints in the repository or its history
- [ ] Demo video recorded (owner)
- [ ] Repository visibility decision (owner)

## Optional future enhancements (not planned)

- JWT/Cognito or IAM authorizer, and per-client rate limits.
- Pagination for `GET /items`.
- Decimal-safe price representation.
- A short, approved deployment smoke test, then deletion of the stack.
- CloudWatch alarms and an AWS Budgets alarm in the template.
- Dependabot or pip-audit, and image digests instead of tags.
- Enabling CI on push and pull requests.
- arm64 Lambda (lower cost).
