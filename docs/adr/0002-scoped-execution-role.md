# ADR 0002: Explicit, scoped Lambda execution role

- **Status:** Accepted (Milestone 5)
- **Context date:** 2026-10-29

## Context

With `Policies:` on the function, SAM generated the execution role and always attached the AWS managed policy `AWSLambdaBasicExecutionRole`. That policy allows `logs:CreateLogGroup`, `logs:CreateLogStream` and `logs:PutLogEvents` on `Resource: "*"`, which covers any log group in the account. IAM grants the union of all attached policies, so adding a narrower inline policy would not have removed this access. The expanded template (offline SAM transform) confirmed the managed policy was attached.

The function already writes to a dedicated log group (`ItemsFunctionLogGroup`, via `LoggingConfig`), and the template creates that group.

## Decision

Declare `ItemsFunctionExecutionRole` in the template and pass it with `Role:`. SAM then creates no role and attaches no managed policy. Its single inline policy allows:

- `dynamodb:GetItem`, `PutItem`, `DeleteItem`, `Scan` on the table ARN;
- `logs:CreateLogStream`, `logs:PutLogEvents` on `arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:<the dedicated group>:log-stream:*`.

`logs:CreateLogGroup` is omitted because the group is created by the template before the function.

The role is named `ItemsFunctionExecutionRole`, not SAM's default `ItemsFunctionRole`, so that if `Policies:` were ever re-added, a second, SAM-generated role would appear and `tests/test_template_iam.py` would fail with a clear assertion.

## Consequences

- No `Resource: "*"` remains in the function's permissions.
- `tests/test_template_iam.py` expands the template offline and asserts: one role, no managed policies, exactly these six action/resource pairs.
- **Not verified in AWS.** That Lambda can write logs with only these permissions follows from the AWS documentation for execution roles and custom log groups, but it hasn't been observed in a deployment. If logs were missing after a deployment, this policy is the first place to look.
- Adding a new AWS call to the code now requires adding its permission to this role.
