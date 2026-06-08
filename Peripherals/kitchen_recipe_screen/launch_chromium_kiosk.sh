#!/usr/bin/env bash

set -euo pipefail

URL="${KITCHEN_SCREEN_URL:-http://127.0.0.1:8765}"

if [[ -n "${CHROMIUM_BIN:-}" ]]; then
  BROWSER="$CHROMIUM_BIN"
elif command -v chromium >/dev/null 2>&1; then
  BROWSER="chromium"
elif command -v chromium-browser >/dev/null 2>&1; then
  BROWSER="chromium-browser"
elif command -v google-chrome >/dev/null 2>&1; then
  BROWSER="google-chrome"
else
  echo "Could not find chromium/google-chrome. Set CHROMIUM_BIN to the browser binary."
  exit 1
fi

exec "$BROWSER" \
  --kiosk \
  --start-fullscreen \
  --incognito \
  --disable-infobars \
  --overscroll-history-navigation=0 \
  --disable-session-crashed-bubble \
  --autoplay-policy=no-user-gesture-required \
  "$URL"
