#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$ROOT_DIR/public"

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

cp "$ROOT_DIR/app/templates/index.html" "$OUT_DIR/index.html"
cp "$ROOT_DIR/app/static/app.js" "$OUT_DIR/app.js"
cp "$ROOT_DIR/app/static/styles.css" "$OUT_DIR/styles.css"
cp "$ROOT_DIR/app/static/favicon.svg" "$OUT_DIR/favicon.svg"

sed -i 's|/static/styles.css|./styles.css|g' "$OUT_DIR/index.html"
sed -i 's|/static/favicon.svg|./favicon.svg|g' "$OUT_DIR/index.html"
sed -i 's|/static/app.js|./app.js|g' "$OUT_DIR/index.html"

# Pages配信時のAPI先を切り替える。未設定時は空文字を入れて、フロント側で明示エラーにする。
API_BASE_URL="${PAGES_API_BASE_URL:-}"
awk -v api_url="$API_BASE_URL" '
  /<script src="\.\/app\.js"><\/script>/ {
    print "  <script>window.__API_BASE_URL = \"" api_url "\";</script>";
  }
  { print }
' "$OUT_DIR/index.html" > "$OUT_DIR/index.tmp" && mv "$OUT_DIR/index.tmp" "$OUT_DIR/index.html"

echo "Built Pages files into $OUT_DIR"
