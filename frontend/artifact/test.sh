#!/usr/bin/env bash
# Tests for the artifact brain. Usage: frontend/artifact/test.sh DATA_JSON
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); FE=$(dirname "$HERE"); TMP=$(mktemp -d)
cd "$FE"
npx --yes esbuild@0.24.0 artifact/brain.test.ts --bundle --platform=node --format=cjs \
  --alias:@=./src --log-level=warning --outfile="$TMP/t.cjs"
node "$TMP/t.cjs" "$1"
