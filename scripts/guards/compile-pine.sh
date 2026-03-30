#!/bin/bash
# Pine Script Real Compiler Guard

if [ -z "$1" ]; then
  echo "Error: Please provide a path to a .pine file."
  echo "Usage: ./scripts/guards/compile-pine.sh indicators/v7-warbird-institutional.pine"
  exit 1
fi

PINE_FILE="$1"

if [ ! -f "$PINE_FILE" ]; then
  echo "Error: File not found: $PINE_FILE"
  exit 1
fi

echo "Compiling $PINE_FILE via TradingView pine-facade API..."

pine_code=$(cat "$PINE_FILE")
response=$(curl -s -X POST "https://pine-facade.tradingview.com/pine-facade/translate_light?user_name=admin&v=3" \
  -H 'Referer: https://www.tradingview.com/' \
  -F "source=$pine_code")

if echo "$response" | grep -q '"success":true'; then
  echo "✅ Compilation SUCCESS!"
  exit 0
else
  echo "❌ Compilation FAILED:"
  echo "$response" | grep -o '"reason":[^}]*' | sed 's/"reason":"//' | sed 's/"$//'
  echo "$response"
  exit 1
fi
