#!/usr/bin/env bash
# Headless Chrome screenshot of the map (served by the API from web/dist). Used to eyeball the UI.
# Usage: scripts/screenshot.sh <base-url> [out.png] [query]   e.g. scripts/screenshot.sh http://localhost:7071 shot.png "?phone=open"
set -euo pipefail
B=${1:-${BASE_URL:-http://localhost:7071}}
OUT=${2:-screenshot.png}
QUERY=${3:-"?phone=open"}
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
command -v google-chrome >/dev/null 2>&1 && CHROME=google-chrome
"$CHROME" --headless=new --hide-scrollbars --window-size=1400,900 --force-device-scale-factor=1 \
  --use-angle=swiftshader --enable-unsafe-swiftshader --ignore-gpu-blocklist \
  --virtual-time-budget=8000 --screenshot="$OUT" "$B/$QUERY" >/dev/null 2>&1
echo "screenshot: $OUT ($(stat -f%z "$OUT") bytes)"
