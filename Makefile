# Local-only targets. None of these create, change or delete AWS resources.
# OFFLINE hides AWS config and credentials and disables SAM telemetry, so a
# command that tries to reach AWS fails instead of using your account.
VENV ?= .venv
BIN := $(VENV)/bin
OFFLINE := env -u AWS_PROFILE -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
	PATH="$(abspath $(BIN)):$$PATH" SAM_CLI_TELEMETRY=0 \
	AWS_CONFIG_FILE=/dev/null AWS_SHARED_CREDENTIALS_FILE=/dev/null \
	AWS_REGION=us-east-1
# Set REPORTS_DIR (as CI does) to also write JUnit XML test reports there.
junit = $(if $(REPORTS_DIR),--junitxml=$(REPORTS_DIR)/$(1).xml)

.PHONY: install lock test lint validate build verify clean \
	local-up local-down local-status test-integration local-test

# Installs exactly the locked, hash-verified tool versions.
install:
	uv venv --allow-existing --python 3.14 $(VENV)
	uv pip sync --python $(BIN)/python --require-hashes requirements-dev.lock

# Re-resolve requirements-dev.lock after editing requirements-dev.txt.
lock:
	uv pip compile requirements-dev.txt --universal --python-version 3.14 --generate-hashes -o requirements-dev.lock

test:
	$(OFFLINE) $(BIN)/python -m pytest $(call junit,unit)

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
	$(OFFLINE) $(BIN)/python -m pytest -m integration -v $(call junit,integration)

# One-shot: start the stack, run integration tests, and always tear down,
# including when startup itself fails. Exits with the first failure's status.
local-test:
	status=0; scripts/local.sh up && $(MAKE) --no-print-directory test-integration || status=$$?; \
	scripts/local.sh down; exit $$status

clean: local-down
	rm -rf .aws-sam .pytest_cache .local
