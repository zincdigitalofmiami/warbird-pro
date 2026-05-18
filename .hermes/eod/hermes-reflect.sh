#!/usr/bin/env bash
set -euo pipefail

HERMES_BIN="/Users/zincdigital/.local/bin/hermes"
REPO="/Volumes/Satechi Hub/warbird-pro"
LOG_DIR="/Users/zincdigital/.hermes/logs"
LOG_FILE="$LOG_DIR/reflection-$(date +%Y%m%d).log"

mkdir -p "$LOG_DIR"

PROMPT='Warbird daily Hermes reflection: inspect recent Hermes/Warbird session summaries and project state. Write 2-5 concise durable memory candidates and 0-2 skill draft ideas under .hermes/skills/drafts if warranted. Do not modify Pine, trainer, ETL, Supabase, or TradingView. Do not promote skills automatically. Report only what was drafted.'

cd "$REPO"
{
  printf '%s Starting Warbird Hermes reflection\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')"
  "$HERMES_BIN" chat -Q --provider openai-codex -m gpt-5.5 -t file,terminal,skills,memory --ignore-rules -q "$PROMPT"
  printf '%s Reflection complete\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')"
} >>"$LOG_FILE" 2>&1
