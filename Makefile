# Local-only targets. None of these create, change or delete AWS resources.
# OFFLINE hides AWS config and credentials and disables SAM telemetry, so a
# command that tries to reach AWS fails instead of using your account.
VENV ?= .venv
BIN := $(VENV)/bin
OFFLINE := env -u AWS_PROFILE -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
	PATH="$(abspath $(BIN)):$$PATH" SAM_CLI_TELEMETRY=0 \
	AWS_CONFIG_FILE=/dev/null AWS_SHARED_CREDENTIALS_FILE=/dev/null \
	AWS_REGION=us-east-1

.PHONY: install test lint validate build verify clean

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

clean:
	rm -rf .aws-sam .pytest_cache
