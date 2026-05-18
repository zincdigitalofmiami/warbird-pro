#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=1
AGGRESSIVE=0

for arg in "$@"; do
  case "$arg" in
    --execute) DRY_RUN=0 ;;
    --dry-run) DRY_RUN=1 ;;
    --aggressive) AGGRESSIVE=1 ;;
    *)
      printf 'Unknown argument: %s\n' "$arg" >&2
      exit 2
      ;;
  esac
done

HERMES_BIN="/Users/zincdigital/.local/bin/hermes"
HERMES_HOME="/Users/zincdigital/.hermes"
LOG_DIR="$HERMES_HOME/logs"
LOG_FILE="$LOG_DIR/eod-$(date +%Y%m%d).log"

mkdir -p "$LOG_DIR"

log() {
  printf '%s %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*" | tee -a "$LOG_FILE"
}

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    log "DRY-RUN: $*"
  else
    log "RUN: $*"
    "$@" >>"$LOG_FILE" 2>&1 || log "WARN: command failed: $*"
  fi
}

log "Warbird Hermes EOD cleanup start (dry_run=$DRY_RUN aggressive=$AGGRESSIVE)"

if [ -x "$HERMES_BIN" ]; then
  run "$HERMES_BIN" gateway stop
else
  log "WARN: Hermes binary not executable at $HERMES_BIN"
fi

if command -v pgrep >/dev/null 2>&1; then
  for pattern in 'agent-browser' 'playwright.*chromium.*hermes' 'hermes.*browser'; do
    if pgrep -f "$pattern" >/dev/null 2>&1; then
      if [ "$DRY_RUN" -eq 1 ]; then
        log "DRY-RUN: terminate processes matching $pattern"
        pgrep -fl "$pattern" | tee -a "$LOG_FILE" || true
      else
        log "RUN: terminate processes matching $pattern"
        pkill -TERM -f "$pattern" || true
      fi
    fi
  done
fi

if [ "$AGGRESSIVE" -eq 1 ] && command -v pgrep >/dev/null 2>&1; then
  for pattern in 'hermes-agent.*gateway' 'run_agent.py.*gateway'; do
    if pgrep -f "$pattern" >/dev/null 2>&1; then
      if [ "$DRY_RUN" -eq 1 ]; then
        log "DRY-RUN: aggressive terminate processes matching $pattern"
        pgrep -fl "$pattern" | tee -a "$LOG_FILE" || true
      else
        log "RUN: aggressive terminate processes matching $pattern"
        pkill -TERM -f "$pattern" || true
      fi
    fi
  done
fi

for dir in "$HERMES_HOME/cache" "$HERMES_HOME/audio_cache" "$HERMES_HOME/image_cache"; do
  if [ -d "$dir" ]; then
    if [ "$DRY_RUN" -eq 1 ]; then
      log "DRY-RUN: prune files older than 7 days in $dir"
    else
      log "RUN: prune files older than 7 days in $dir"
      find "$dir" -type f -mtime +7 -delete >>"$LOG_FILE" 2>&1 || true
    fi
  fi
done

STATE_DB="$HERMES_HOME/state.db"
if [ -f "$STATE_DB" ]; then
  size_bytes=$(stat -f%z "$STATE_DB" 2>/dev/null || stat -c%s "$STATE_DB" 2>/dev/null || printf '0')
  if [ "$size_bytes" -gt 524288000 ]; then
    run sqlite3 "$STATE_DB" 'VACUUM;'
  else
    log "state.db below vacuum threshold (${size_bytes} bytes)"
  fi
fi

log "Warbird Hermes EOD cleanup complete"
