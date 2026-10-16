#!/usr/bin/env bash
# Public URL for the local host + Twilio webhooks in one go. Re-run whenever the phone says "application error".
cd "$(dirname "$0")"
LOG=$(mktemp)
cloudflared tunnel --url http://localhost:7071 > "$LOG" 2>&1 &
for i in $(seq 1 40); do
  URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG" | head -1)
  [ -n "$URL" ] && grep -q "Registered tunnel" "$LOG" && break
  sleep 1
done
[ -z "$URL" ] && { echo "tunnel failed:"; tail -5 "$LOG"; exit 1; }
./set_webhooks.sh "$URL"
echo "tunnel up, Ctrl-C to stop"; wait
