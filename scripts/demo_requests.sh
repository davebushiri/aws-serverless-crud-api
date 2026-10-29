#!/usr/bin/env bash
# Walk through the CRUD workflow against the local API and print each request
# and response. Requires `make local-up`. Usage: scripts/demo_requests.sh
set -euo pipefail
API=${LOCAL_API_URL:-http://127.0.0.1:3000}
case "$API" in http://127.0.0.1:*|http://localhost:*) ;; *) echo "Refusing non-local API $API" >&2; exit 1 ;; esac

step() {
  local title=$1 method=$2 path=$3 body=${4:-}
  printf '\n### %s\n$ curl -X %s %s%s%s\n' "$title" "$method" "$API" "$path" "${body:+ -d '$body'}"
  if [ -n "$body" ]; then
    curl -s -X "$method" "$API$path" -H 'Content-Type: application/json' --data "$body" -w '\nHTTP %{http_code}\n'
  else
    curl -s -X "$method" "$API$path" -w '\nHTTP %{http_code}\n'
  fi
}

echo "Local HTTP API run: $(date -u +%Y-%m-%dT%H:%M:%SZ)  ($API)"
step "1. Create item"          PUT    /items        '{"id": "demo-1", "price": 19.99, "name": "Widget"}'
step "2. Retrieve item"        GET    /items/demo-1
step "3. Retrieve all items"   GET    /items
step "4. Update item"          PUT    /items        '{"id": "demo-1", "price": 24.5, "name": "Widget Pro"}'
step "5. Retrieve updated"     GET    /items/demo-1
step "6. Delete item"          DELETE /items/demo-1
step "7. Confirm deletion"     GET    /items/demo-1
step "8. List after delete"    GET    /items
