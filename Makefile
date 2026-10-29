# Local-only targets. None of these create, change or delete AWS resources.
# OFFLINE hides AWS config and credentials and disables SAM telemetry, so a
# command that tries to reach AWS fails instead of using your account.
VENV ?= .venv
BIN := $(VENV)/bin
OFFLINE := env -u AWS_PROFILE -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
	PATH="$(abspath $(BIN)):$$PATH" SAM_CLI_TELEMETRY=0 \
	AWS_CONFIG_FILE=/dev/null AWS_SHARED_CREDENTIALS_FILE=/dev/null \
	AWS_REGION=us-east-1

.PHONY: install test lint validate build verify clean \
	local-up local-down local-status test-integration local-test

install:
	uv venv --python 3.14 $(VENV)
	uv pip install --python $(BIN)/python -r requirements-dev.txt

test:
	$(OFFLINE) $(BIN)/python -m pytest

lint:
	$(OFFLINE) $(BIN)/cfn-lint template.yaml

validate:
	$(OFFLINE) $(BIN)/sam validate --lint

build:
	$(OFFLINE) $(BIN)/sam build

verify: test lint validate build

# Local stack (needs Docker): DynamoDB Local + sam local start-api on :3000.
local-up:
	scripts/local.sh up

local-down:
	scripts/local.sh down

local-status:
	scripts/local.sh status

test-integration:
	$(OFFLINE) $(BIN)/python -m pytest -m integration -v

# One-shot: start the stack, run integration tests, always tear down.
local-test:
	scripts/local.sh up && { $(MAKE) --no-print-directory test-integration; status=$$?; scripts/local.sh down; exit $$status; }

clean: local-down
	rm -rf .aws-sam .pytest_cache .local
