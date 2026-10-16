#!/usr/bin/env bash
# Simulates Twilio against a running host (func start). Works without TTS models (falls back to <Say>).
set -e
B=${1:-http://localhost:7071/api}
F=%2B49151$RANDOM$RANDOM   # a caller we have never seen
curl -sf -X POST "$B/voice" -d From=$F | grep -q "voice/lang"                                        # first call: language menu
curl -sf -X POST "$B/voice/lang" -d From=$F -d Digits=2 | grep -q "en-US"                           # 2 = English
curl -sf -X POST "$B/voice" -d From=$F | grep -q "en-US"                                             # remembered: no menu
curl -sf -X POST "$B/voice/lang" -d From=$F -d Digits=3 | grep -q "de-DE"                           # 3 = German
curl -sf -X POST "$B/voice/lang" -d From=$F -d Digits=4 | grep -q "fr-FR"                           # 4 = French
curl -sf -X POST "$B/voice/handle?lang=en&n=1" -d From=$F -d SpeechResult="blah" | grep -q "n=2"    # nothing understood: retry
curl -sf -X POST "$B/voice/handle?lang=en&n=2" -d From=$F -d SpeechResult="" | grep -q "n=3"        # said nothing: retry again
curl -sf -X POST "$B/voice/handle?lang=en&n=3" -d From=$F -d SpeechResult="blah" | grep -q "<Hangup"  # third miss: give up
curl -sf -X POST "$B/voice/handle?lang=en&n=1" -d From=$F -d SpeechResult="The Cibari spring is broken" -d Confidence=0.3 | grep -q "voice/confirm"
curl -sf -X POST "$B/voice/confirm?lang=en&text=The%20Cibari%20spring%20is%20broken&turn=smoke-confirm" -d From=$F -d Digits=1 | grep -q "voice/another"
curl -sf -X POST "$B/voice/handle?lang=en&n=1" -d From=$F -d SpeechResult="The Cibari spring is broken" -d Confidence=0.9 | grep -qE "<Play>|<Say"
curl -sf -X POST "$B/voice/handle?lang=de&n=1" -d From=$F -d SpeechResult="Gatovu spring ist kaputt" -d Confidence=0.9 | grep -q "voice/another"
curl -sf -X POST "$B/voice/another?lang=en" -d From=$F -d Digits=1 | grep -q "en-US"                # 1 = report another
curl -sf -X POST "$B/sms" -d From=%2B4915112345678 -d Body="Burima spring imeharibika" | grep -qi "imeandikwa"
curl -sf -X POST "$B/sms" -d From=%2B4915112345678 --data-urlencode "Body=Men harass women on the way from Kayenzi to Kayenzi spring" | grep -q "identity is protected"
curl -sf "$B/events" | grep -q '"kind": "harassment"'                                              # the map draws it
curl -sf "$B/events" | python3 -c "import json,sys; e=[e for e in json.load(sys.stdin)['events'] if 'harass' in e['body']]; assert e and all(x['sender'].startswith('caller-') for x in e)"  # no number on a hazard
curl -sf "$B/events" | grep -q "Karemera spring, about [0-9]* minutes"
curl -sf -X POST "$B/interact" -H "Content-Type: application/json" -d '{"message":"Is Cibari spring working?","lang":"en"}' | grep -q '"answer"'   # JSON API, same brain
curl -sf "$B/dashboard" | grep -q 'id="root"'   # web/dist built
echo "smoke ok"
