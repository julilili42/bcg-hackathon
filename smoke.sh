#!/usr/bin/env bash
# Simuliert Twilio-Webhooks gegen den lokalen Host. Vorher: func start
set -e
B=${1:-http://localhost:7071/api}
curl -sf -X POST "$B/sms"   -d From=%2B4915112345678 -d Body="AVOCADO GULU" | grep -q "Received: AVOCADO GULU"
curl -sf -X POST "$B/voice" | grep -q "<Gather"
curl -sf -X POST "$B/voice" -d From=%2B4915112345678 -d Digits=1 | grep -q "Received: 1"
curl -sf "$B/events" | grep -q '"body": "AVOCADO GULU"'
echo "smoke ok"
