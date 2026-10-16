#!/usr/bin/env bash
# Simulates Twilio against a running host (func start). Works without TTS models (falls back to <Say>).
set -e
B=${1:-http://localhost:7071/api}
curl -sf -X POST "$B/voice" | grep -q "<Gather"
curl -sf -X POST "$B/voice/handle?lang=sw" -d Digits=2 | grep -q "en-US"
curl -sf -X POST "$B/voice/handle?lang=en" -d From=%2B4915112345678 -d SpeechResult="The Shule well is broken" | grep -qE "<Play>|<Say"
curl -sf -X POST "$B/sms" -d From=%2B4915112345678 -d Body="Shule imeharibika" | grep -q "imeandikwa"
curl -sf "$B/events" | grep -q "Kanisa, [0-9]* minutes"
echo "smoke ok"
