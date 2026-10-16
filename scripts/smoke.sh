#!/usr/bin/env bash
# Simulates Twilio against a running host (func start). Works without TTS models (falls back to <Say>).
set -e
B=${1:-http://localhost:7071/api}
F=%2B49151$RANDOM$RANDOM   # a caller we have never seen
curl -sf -X POST "$B/voice" -d From=$F | grep -q "voice/lang"                                        # first call: language menu
curl -sf -X POST "$B/voice/lang" -d From=$F -d Digits=2 | grep -q "en-US"                           # 2 = English
curl -sf -X POST "$B/voice" -d From=$F | grep -q "en-US"                                             # remembered: no menu
curl -sf -X POST "$B/voice/lang" -d From=$F -d Digits=3 | grep -q "de-DE"                           # 3 = German
curl -sf -X POST "$B/voice/handle?lang=en&n=1" -d From=$F -d SpeechResult="blah" | grep -q "n=2"    # nothing understood: retry
curl -sf -X POST "$B/voice/handle?lang=en&n=2" -d From=$F -d SpeechResult="" | grep -q "n=3"        # said nothing: retry again
curl -sf -X POST "$B/voice/handle?lang=en&n=3" -d From=$F -d SpeechResult="blah" | grep -q "<Hangup"  # third miss: give up
curl -sf -X POST "$B/voice/handle?lang=en&n=1" -d From=$F -d SpeechResult="The Zahanati well is broken" -d Confidence=0.3 | grep -q "voice/confirm"
curl -sf -X POST "$B/voice/confirm?lang=en&text=The%20Zahanati%20well%20is%20broken&turn=smoke-confirm" -d From=$F -d Digits=1 | grep -q "voice/another"
curl -sf -X POST "$B/voice/handle?lang=en&n=1" -d From=$F -d SpeechResult="The Zahanati well is broken" -d Confidence=0.9 | grep -qE "<Play>|<Say"
curl -sf -X POST "$B/voice/handle?lang=de&n=1" -d From=$F -d SpeechResult="Rabo ist kaputt" -d Confidence=0.9 | grep -q "voice/another"
curl -sf -X POST "$B/voice/another?lang=en" -d From=$F -d Digits=1 | grep -q "en-US"                # 1 = report another
curl -sf -X POST "$B/sms" -d From=%2B4915112345678 -d Body="Zahanati imeharibika" | grep -qi "imeandikwa"
curl -sf "$B/events" | grep -q "Mama Nasa, [0-9]* minutes"
curl -sf -X POST "$B/interact" -H "Content-Type: application/json" -d '{"message":"Is Zahanati working?","lang":"en"}' | grep -q '"answer"'   # JSON API, same brain
curl -sf "$B/dashboard" | grep -q 'id="root"'   # web/dist built
echo "smoke ok"
