#!/usr/bin/env bash
# Reset live reports before a rehearsal (keeps imported baselines and demo aliases).
# Usage: scripts/demo_reset.sh [http://localhost:7071]   Needs ADMIN_TOKEN in api/local.settings.json or env.
set -euo pipefail
B=${1:-http://localhost:7071}
HERE=$(cd "$(dirname "$0")/.." && pwd)
TOKEN=${ADMIN_TOKEN:-$(python3 -c "import json;print(json.load(open('$HERE/api/local.settings.json'))['Values'].get('ADMIN_TOKEN',''))" 2>/dev/null || true)}
[ -n "$TOKEN" ] || { echo "ADMIN_TOKEN not set"; exit 1; }
curl -sf -X POST "$B/api/admin/reset?mode=live" -H "X-Admin-Token: $TOKEN"
echo
echo "Re-applying demo overlay baselines..."
cd "$HERE" && PYTHONPATH=api uv run python -m reach.ingest.seed >/dev/null && echo "demo state restored"
