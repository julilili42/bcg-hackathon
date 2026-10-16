#!/usr/bin/env bash
# Point the Twilio number at a public URL (your tunnel or the Azure Function).
# Usage: scripts/set_webhooks.sh https://xyz.trycloudflare.com
# Reads TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN from local.settings.json.
set -e
cd "$(dirname "$0")/.."
URL=${1:?usage: $0 https://public-host}
SID=$(python3 -c "import json;print(json.load(open('local.settings.json'))['Values']['TWILIO_ACCOUNT_SID'])")
TOK=$(python3 -c "import json;print(json.load(open('local.settings.json'))['Values']['TWILIO_AUTH_TOKEN'])")
API="https://api.twilio.com/2010-04-01/Accounts/$SID"
PN=$(curl -sf -u "$SID:$TOK" "$API/IncomingPhoneNumbers.json" | python3 -c "import json,sys;print(json.load(sys.stdin)['incoming_phone_numbers'][0]['sid'])")
curl -sf -u "$SID:$TOK" -X POST "$API/IncomingPhoneNumbers/$PN.json" \
  -d VoiceUrl="$URL/api/voice" -d VoiceMethod=POST -d SmsUrl="$URL/api/sms" -d SmsMethod=POST \
  | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['phone_number']);print(' voice ->',d['voice_url']);print(' sms   ->',d['sms_url'])"
# Browser phone (TwiML App), if scripts/phone_setup.py has been run
APP=$(python3 -c "import json;print(json.load(open('local.settings.json'))['Values'].get('TWILIO_APP_SID',''))")
[ -n "$APP" ] && curl -sf -u "$SID:$TOK" -X POST "$API/Applications/$APP.json" -d VoiceUrl="$URL/api/voice" -d VoiceMethod=POST \
  | python3 -c "import json,sys;d=json.load(sys.stdin);print('browser phone ->',d['voice_url'])"
