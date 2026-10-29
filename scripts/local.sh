#!/usr/bin/env bash
# Local stack: DynamoDB Local (Docker) + the Lambda behind `sam local start-api`.
# Usage: scripts/local.sh {up|down|status}
#
# Everything runs with synthetic credentials and with AWS config files hidden,
# so nothing here can authenticate to a real AWS account.
set -euo pipefail
cd "$(dirname "$0")/.."

NETWORK=items-local-net
DDB_CONTAINER=items-dynamodb-local
DDB_IMAGE=amazon/dynamodb-local:3.3.2
LAMBDA_IMAGE=public.ecr.aws/lambda/python:3.14-x86_64
DDB_PORT=${DDB_PORT:-8000}
API_PORT=${API_PORT:-3000}
STATE_DIR=.local
PID_FILE=$STATE_DIR/sam-api.pid
LOG_FILE=$STATE_DIR/sam-api.log
BIN=$PWD/.venv/bin

unset AWS_PROFILE AWS_SESSION_TOKEN
export PATH="$BIN:$PATH" SAM_CLI_TELEMETRY=0 \
  AWS_CONFIG_FILE=/dev/null AWS_SHARED_CREDENTIALS_FILE=/dev/null \
  AWS_ACCESS_KEY_ID=local AWS_SECRET_ACCESS_KEY=local \
  AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1 \
  LOCAL_DYNAMODB_URL=http://127.0.0.1:$DDB_PORT

log() { printf '==> %s\n' "$*"; }

wait_for_api() {
  for _ in $(seq 1 120); do
    if curl -sf -o /dev/null "http://127.0.0.1:$API_PORT/items"; then return 0; fi
    if ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "sam local start-api exited; see $LOG_FILE" >&2; tail -20 "$LOG_FILE" >&2; return 1
    fi
    sleep 1
  done
  echo "Timed out waiting for the local API; see $LOG_FILE" >&2
  return 1
}

up() {
  docker info >/dev/null 2>&1 || { echo "Docker is not running." >&2; exit 1; }
  [ -x "$BIN/sam" ] || { echo "Run 'make install' first." >&2; exit 1; }
  mkdir -p "$STATE_DIR"
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Already running (pid $(cat "$PID_FILE")). Run 'make local-down' first." >&2; exit 1
  fi

  log "Docker network $NETWORK"
  docker network inspect "$NETWORK" >/dev/null 2>&1 || docker network create "$NETWORK" >/dev/null

  log "DynamoDB Local ($DDB_IMAGE, in-memory) on 127.0.0.1:$DDB_PORT"
  docker rm -f "$DDB_CONTAINER" >/dev/null 2>&1 || true
  docker run -d --name "$DDB_CONTAINER" --network "$NETWORK" -p "127.0.0.1:$DDB_PORT:8000" \
    "$DDB_IMAGE" -jar DynamoDBLocal.jar -inMemory -sharedDb >/dev/null
  "$BIN/python" scripts/local_table.py wait
  "$BIN/python" scripts/local_table.py reset

  log "Lambda runtime image"
  docker image inspect "$LAMBDA_IMAGE" >/dev/null 2>&1 || docker pull -q "$LAMBDA_IMAGE"

  log "sam build"
  sam build >"$STATE_DIR/sam-build.log" 2>&1 || { cat "$STATE_DIR/sam-build.log" >&2; exit 1; }

  log "sam local start-api on http://127.0.0.1:$API_PORT"
  nohup sam local start-api \
    --host 127.0.0.1 --port "$API_PORT" \
    --env-vars local/env.json \
    --docker-network "$NETWORK" \
    --warm-containers EAGER \
    --skip-pull-image \
    >"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
  wait_for_api
  log "Ready: http://127.0.0.1:$API_PORT/items   (logs: $LOG_FILE)"
}

down() {
  if [ -f "$PID_FILE" ]; then
    pid=$(cat "$PID_FILE")
    if kill -0 "$pid" 2>/dev/null; then
      log "Stopping sam local start-api (pid $pid)"
      kill "$pid"
      for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
  fi
  # Warm Lambda containers left behind if SAM was killed abruptly.
  leftovers=$(docker ps -aq --filter "network=$NETWORK" 2>/dev/null || true)
  [ -n "$leftovers" ] && docker rm -f $leftovers >/dev/null
  log "Removing $DDB_CONTAINER and network $NETWORK"
  docker rm -f "$DDB_CONTAINER" >/dev/null 2>&1 || true
  docker network rm "$NETWORK" >/dev/null 2>&1 || true
}

status() {
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "API: running (pid $(cat "$PID_FILE")) at http://127.0.0.1:$API_PORT"
  else
    echo "API: stopped"
  fi
  docker ps --filter "network=$NETWORK" --format 'container: {{.Names}} ({{.Image}}) {{.Status}}' 2>/dev/null || true
}

case "${1:-}" in
  up) up ;;
  down) down ;;
  status) status ;;
  *) echo "Usage: $0 {up|down|status}" >&2; exit 2 ;;
esac
