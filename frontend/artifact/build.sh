#!/usr/bin/env bash
# Standalone Jarvis page (artifact): the real frontend + answers recorded from the backend.
# Usage: frontend/artifact/build.sh OUT_DIR   (backend must be running on :8000)
# Publish OUT_DIR/index.html with app.js, snapshot.json and data.json, and
# capabilities {sample: {}, tts: {}, dictation: {}}.
set -euo pipefail
OUT=${1:?output dir}; HERE=$(cd "$(dirname "$0")" && pwd); FE=$(dirname "$HERE")
mkdir -p "$OUT"
python3 "$HERE/record.py" "$OUT/snapshot.json"
(cd "$FE/../backend" && uv run python "$HERE/record_data.py" "$OUT/data.json")
"$HERE/test.sh" "$OUT/data.json"
cd "$FE"
npx --yes esbuild@0.24.0 artifact/entry.tsx --bundle --minify --charset=ascii --format=iife --jsx=automatic \
  --alias:next/dynamic=./artifact/shims/next-dynamic.tsx --alias:next/link=./artifact/shims/next-link.tsx \
  --alias:@=./src --define:process.env.NODE_ENV='"production"' \
  --define:process.env.NEXT_PUBLIC_API_URL='"snapshot"' --outfile="$OUT/app.js"
awk '/\/\* GLOBALS \*\//{system("cat src/app/globals.css");next}1' "$HERE/page.html" > "$OUT/index.html"
echo "built $OUT"
