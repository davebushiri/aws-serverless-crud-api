# Continuous integration

Workflow: [`.github/workflows/ci.yml`](../.github/workflows/ci.yml). One job on a standard `ubuntu-24.04` runner:

1. Check out the repo (`persist-credentials: false`).
2. Set up Python 3.14 and uv 0.11.32.
3. Check that Docker is available.
4. `make install` installs the locked, hash-verified tools from `requirements-dev.lock`.
5. Print tool versions and **assert that no AWS credentials exist**.
6. `make verify`: unit tests, cfn-lint, `sam validate --lint`, `sam build`.
7. `make local-test`: DynamoDB Local + `sam local start-api`, then the integration tests and teardown.
8. Always: write a test summary table to the run page, upload the test reports and SAM log **only on failure** (kept 5 days), then remove containers, the network and temporary files.

Any failing test, lint, validation or build step fails the job.

## Security

| Control | How |
| --- | --- |
| Least-privilege token | `permissions: contents: read` for the whole workflow |
| No AWS access | No secrets, no OIDC role; AWS config files are set to `/dev/null`; the run checks that boto3 finds no credentials; local tests use synthetic `local`/`local` keys |
| No untrusted-code privilege | Triggers are `workflow_dispatch` (and later `push`/`pull_request`); never `pull_request_target` |
| Pinned dependencies | Actions pinned to full commit SHAs (the release tag is in a comment); Python tools pinned and hash-verified through `requirements-dev.lock` |
| Emulators not exposed | DynamoDB Local and the API bind to `127.0.0.1` only |
| Checkout token not left on disk | `persist-credentials: false` |
| Static checks | `actionlint` (with shellcheck) and `zizmor --offline` reported no findings for this workflow |

## Cost controls

- **Manual only for now.** The `push` and `pull_request` triggers are commented out until a spending budget is confirmed.
- **Bounded runs:** one job, a standard 2-core Linux runner (1x minute multiplier), no matrix, `timeout-minutes: 20`, and a `concurrency` group that cancels a superseded run on the same ref.
- **Small storage:** artifacts only on failure, kept 5 days. The uv cache is keyed on the lock file.

GitHub bills private-repository Actions usage per minute beyond the plan's included minutes. Public repositories on standard runners are free. Check your current included minutes and usage on GitHub, because plan allowances change.

### Set a hard spending stop (do this before enabling push/PR triggers)

1. GitHub → **Settings → Billing and licensing → Budgets and alerts**.
2. Create a budget for the **Actions** product with an amount of **$0**.
3. Turn on **"Stop usage when budget limit is reached"**, and add an alert email.
4. Under **Billing → Usage**, confirm the included Actions minutes and what you've used this month.

With a $0 stop-usage budget, runs stop once the included minutes are used up, instead of being billed.

## Verified run

[Run 40825291736](https://github.com/davebushiri/aws-serverless-crud-api/actions/runs/40825291736): `workflow_dispatch` on commit `9e7d255`, **success**, job duration 72 s on `ubuntu-24.04`.

| Step | Result |
| --- | --- |
| Docker | client and server 28.0.4 available |
| `make install` | 90 locked packages installed with hashes verified; CPython 3.14.9 from setup-python |
| Credentials check | `AWS credentials: none` |
| Unit tests | 17 passed |
| cfn-lint / `sam validate --lint` / `sam build` | clean / valid / succeeded |
| Integration tests (`make local-test`) | 10 passed, 4 `LegacyUnhandledError` warnings (the known crash cases) |
| Cleanup | DynamoDB Local container and network removed; no leftover containers |
| Failure artifacts | skipped (upload runs only on failure) |
| Job log scan | no credentials or tokens; the only AWS host is `public.ecr.aws` (anonymous Lambda image pull) |

Before pushing, the same steps were rehearsed locally in a clean clone. Three deliberate breakages confirmed the checks fail when they should: a behavior change failed `make verify` and `make local-test`; a startup failure (port taken) failed and still removed all containers; and the crash assertion rejected 5 malformed responses.

## Running CI

- **GitHub UI:** Actions → **CI** → **Run workflow** → branch `main`.
- **CLI:** `gh workflow run ci.yml --ref main`, then `gh run watch`.
- **Same steps locally:** `REPORTS_DIR=reports make install verify local-test`.

## Changing tool versions

Edit `requirements-dev.txt`, then run `make lock`, run `make install verify local-test`, and commit both files. Bump action SHAs to a release that has been public for at least about two weeks.
