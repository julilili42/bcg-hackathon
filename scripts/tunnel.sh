#!/usr/bin/env bash
# Public URL for the local host + Twilio webhooks in one go. Re-run whenever the phone says "application error".
# With GEMINI_API_KEY in local.settings.json a second tunnel goes to the Gemini voice bridge (uv run -m gateway.live, :7072)
# and calls go there; SMS stays on the Function.
cd "$(dirname "$0")/.."
PIDS=$(mktemp)  # tunnel() runs in a $(...) subshell, so a plain `wait` would not see its cloudflared: keep the pids
trap 'kill $(cat "$PIDS") 2>/dev/null' EXIT
tunnel() {  # port -> prints the public URL once the tunnel is registered
  local log; log=$(mktemp)
  cloudflared tunnel --url "http://localhost:$1" > "$log" 2>&1 &
  echo $! >> "$PIDS"
  for i in $(seq 1 40); do
    local url; url=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$log" | head -1)
    [ -n "$url" ] && grep -q "Registered tunnel" "$log" && { echo "$url"; return; }
    sleep 1
  done
  echo "tunnel to :$1 failed:" >&2; tail -5 "$log" >&2; return 1
}
URL=$(tunnel 7071) || exit 1
if python3 -c "import json,sys;sys.exit(not json.load(open('local.settings.json'))['Values'].get('GEMINI_API_KEY'))"; then
  VOICE_URL=$(tunnel 7072) || exit 1
  export VOICE_URL
  curl -s -o /dev/null --max-time 2 -X POST "http://localhost:7072/voice" || echo "warning: start the voice bridge: uv run -m gateway.live"
fi
scripts/set_webhooks.sh "$URL" "$@"
echo "tunnel up, Ctrl-C to stop"
while kill -0 $(cat "$PIDS") 2>/dev/null; do sleep 5; done  # ends when a tunnel dies: run it again
