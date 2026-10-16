#!/usr/bin/env bash
# Point a Twilio number at a public URL (your tunnel or the Azure Function).
# Usage: scripts/set_webhooks.sh https://xyz.trycloudflare.com            # first number in the account + browser phone
#        scripts/set_webhooks.sh https://xyz.trycloudflare.com +1865...   # that number only (a teammate's own line)
# Reads TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN from local.settings.json.
set -e
cd "$(dirname "$0")/.."
URL=${1:?usage: $0 https://public-host [+1number]}
NUMBER=${2:-}
SID=$(python3 -c "import json;print(json.load(open('local.settings.json'))['Values']['TWILIO_ACCOUNT_SID'])")
TOK=$(python3 -c "import json;print(json.load(open('local.settings.json'))['Values']['TWILIO_AUTH_TOKEN'])")
API="https://api.twilio.com/2010-04-01/Accounts/$SID"
PN=$(curl -sf -u "$SID:$TOK" "$API/IncomingPhoneNumbers.json" | NUMBER="$NUMBER" python3 -c "
import json,sys,os
nums=json.load(sys.stdin)['incoming_phone_numbers']; want=os.environ['NUMBER']
hit=[n for n in nums if not want or n['phone_number']==want]
if not hit: sys.exit(f'number {want} not in this account: {[n[\"phone_number\"] for n in nums]}')
print(hit[0]['sid'])")
curl -sf -u "$SID:$TOK" -X POST "$API/IncomingPhoneNumbers/$PN.json" \
  -d VoiceUrl="$URL/api/voice" -d VoiceMethod=POST -d SmsUrl="$URL/api/sms" -d SmsMethod=POST \
  | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['phone_number']);print(' voice ->',d['voice_url']);print(' sms   ->',d['sms_url'])"
# Browser phone (TwiML App), only when no specific number was given: there is one browser phone, it follows the main line
[ -n "$NUMBER" ] && exit 0
APP=$(python3 -c "import json;print(json.load(open('local.settings.json'))['Values'].get('TWILIO_APP_SID',''))")
[ -n "$APP" ] && curl -sf -u "$SID:$TOK" -X POST "$API/Applications/$APP.json" -d VoiceUrl="$URL/api/voice" -d VoiceMethod=POST \
  | python3 -c "import json,sys;d=json.load(sys.stdin);print('browser phone ->',d['voice_url'])"
