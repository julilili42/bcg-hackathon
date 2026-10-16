#!/usr/bin/env bash
# Point the shared Twilio number at a public URL (your cloudflared tunnel or the Azure Function).
# Usage: scripts/set_webhooks.sh https://xyz.trycloudflare.com
# Reads TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN from api/local.settings.json. Only the demo owner runs this.
set -euo pipefail
URL=${1:?usage: $0 https://public-host}
HERE=$(cd "$(dirname "$0")/.." && pwd)
SETTINGS="$HERE/api/local.settings.json"
SID=$(python3 -c "import json;print(json.load(open('$SETTINGS'))['Values']['TWILIO_ACCOUNT_SID'])")
TOK=$(python3 -c "import json;print(json.load(open('$SETTINGS'))['Values']['TWILIO_AUTH_TOKEN'])")
API="https://api.twilio.com/2010-04-01/Accounts/$SID"
PN=$(curl -sf -u "$SID:$TOK" "$API/IncomingPhoneNumbers.json" | python3 -c "import json,sys;print(json.load(sys.stdin)['incoming_phone_numbers'][0]['sid'])")
curl -sf -u "$SID:$TOK" -X POST "$API/IncomingPhoneNumbers/$PN.json" \
  -d VoiceUrl="$URL/api/voice" -d VoiceMethod=POST -d SmsUrl="$URL/api/sms" -d SmsMethod=POST \
  | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['phone_number']);print(' voice ->',d['voice_url']);print(' sms   ->',d['sms_url'])"
echo "Remember: TWILIO_VALIDATE=1 and PUBLIC_BASE_URL=$URL on the machine that serves this URL."
