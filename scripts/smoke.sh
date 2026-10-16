#!/usr/bin/env bash
# Replays Twilio-shaped requests and web API calls against a running host.
# Usage: scripts/smoke.sh http://localhost:7071   (make dev + make seed first; TWILIO_VALIDATE=0)
set -euo pipefail
B=${1:-http://localhost:7071}
FROM="From=%2B15005550006"   # Twilio magic test number, never a real person
step() { printf '%-48s' "$1"; }
ok() { echo "ok"; }

step "health"; curl -sf "$B/api/health" | grep -q '"status":"ok"' && ok
step "voice greeting gathers sw-TZ"; curl -sf -X POST "$B/api/voice" -d "$FROM" | grep -q 'language="sw-TZ"' && ok
step "press 2 switches to en-US"; curl -sf -X POST "$B/api/voice/handle?lang=sw&domain=water" -d "$FROM" -d Digits=2 | grep -q 'language="en-US"' && ok
step "sms sw report records + alternative"; curl -sf -X POST "$B/api/sms" -d "$FROM" -d "Body=Shule imeharibika" | grep -q "imeandikwa kama imeharibika" && ok
step "sms en query answers"; curl -sf -X POST "$B/api/sms" -d "$FROM" -d "Body=Is Shule working?" | grep -q "Shule is" && ok
step "voice en report replies with audio or Say"; curl -sf -X POST "$B/api/voice/handle?lang=en&domain=water" -d "$FROM" -d "SpeechResult=Shule is working again" | grep -qE "<Play>|<Say" && ok
step "sms health domain"; curl -sf -X POST "$B/api/sms" -d "$FROM" -d "Body=Zahanati Msanga imefungwa" | grep -q "imeandikwa" && ok
step "entities geojson"; curl -sf "$B/api/entities?domain=water" | grep -q '"type":"FeatureCollection"' && ok
step "stats"; curl -sf "$B/api/stats?domain=water" | grep -q people_affected && ok
step "reports feed shows the sms report"; curl -sf "$B/api/reports?domain=water&limit=5" | grep -q '"entity_name"' && ok
echo "smoke ok"
