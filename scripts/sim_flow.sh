#!/usr/bin/env bash
# Replays what the virtual demo phone does in the browser: call -> "hakuna maji" -> "Bwawa" -> SMS query.
# Usage: scripts/sim_flow.sh http://localhost:7071   (or: scripts/with_server.py -- scripts/sim_flow.sh)
set -euo pipefail
B=${1:-${BASE_URL:-http://localhost:7071}}
act() { sed -E 's/.*action="([^"]+)".*/\1/' | sed 's/&amp;/\&/g'; }
say() { grep -o '<Say>[^<]*' | head -1 | sed 's/<Say>//'; }
start=$(curl -sf -X POST "$B/api/sim/voice" -d From=%2B15005550006)
echo "reach:  $(echo "$start" | say)"
a1=$(echo "$start" | act)
echo "caller: hakuna maji"
r1=$(curl -sf -X POST "$B$a1" -d From=%2B15005550006 --data-urlencode "SpeechResult=hakuna maji")
echo "reach:  $(echo "$r1" | say)"
a2=$(echo "$r1" | act)
echo "caller: Bwawa"
r2=$(curl -sf -X POST "$B$a2" -d From=%2B15005550006 --data-urlencode "SpeechResult=Bwawa")
echo "reach:  $(echo "$r2" | say)"
echo "$r2" | grep -q "<Hangup/>" && echo "        (call ended)"
echo "sms:    Is Bwawa working?"
sms=$(curl -sf -X POST "$B/api/sim/sms" -d From=%2B15005550007 --data-urlencode "Body=Is Bwawa working?")
echo "reach:  $(echo "$sms" | grep -o '<Message>[^<]*' | sed 's/<Message>//')"
echo "health: $(curl -sf "$B/api/health" | grep -o '"demo_phone":[a-z]*')"
