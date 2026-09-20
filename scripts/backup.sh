#!/bin/bash
#
# OpenClaw nightly backup — MacBook Air (the production host, per ADR-043)
# Per ADR-019. Runs as user 'sheldonwheeler' at 04:00 ET.
#
# ADR-046 F1 remediation (2026-09-20): the destination was moved out of
# ~/Documents/Mac-Mini-Backups-Interim, in use since 2026-05-17 and a standing
# DATA_BOUNDARIES.md §2 violation, into ~/openclaw/backups — already sanctioned
# by ADR-040 §1. See "Paths" below for why not iCloud, and for the off-device
# weakness this accepts.
#
# NOTE: two other ADR-019 interim deviations are NOT reverted and are now
# permanent — this runs as 'sheldonwheeler' rather than the ADR-020 'dev'
# account, and under launchd rather than cron. Both were scoped to revert on
# "Mac Studio setup day"; ADR-043 established that day never arrives. The
# 'dev' account does not exist on this host (ADR-046 F5).
#
# Behavior:
#   1. pg_dump (compressed -Z 9) the openclaw database to:
#      $BACKUP_DIR/openclaw_YYYYMMDD_HHMMSS.sql.gz
#   2. Write a log line to:
#      $LOG_DIR/backup_YYYYMMDD.log
#   3. Apply 30-day retention to $BACKUP_DIR per ADR-031 §7.
#   4. On any failure, send a Telegram message to the operator via the router bot.
#
# Exit codes:
#   0   success
#   2   pg_dump failed
#   3   destination folder unreachable (path missing or not creatable)
#   4   docker not running or postgres container not up
#
# Telegram alert: the script reads the router bot token and operator chat id
# from the macOS Keychain (per ADR-039 A1 closure, Entry #008). If Keychain
# lookup fails, the script still writes to the log file and exits non-zero —
# the operator finds the gap on next Sunday review.

set -u  # treat unset variables as errors

# ── Paths ────────────────────────────────────────────────────────────
# ADR-046 F1, Option C (2026-09-20). Backups are written inside ~/openclaw,
# which ADR-040 §1 already sanctions read/write/execute. No boundary crossing
# and no TCC grant required.
#
# Why not iCloud. The original ADR-019 destination was
# ~/Library/Mobile Documents/.../Mac-Mini-Backups. launchd-spawned scripts
# cannot write there without a TCC grant (Entry #013). TCC attributes access
# to the *executing binary*, which for a shell script is /bin/bash — so the
# grant would hand full disk access to every bash script on the machine,
# including the §2-prohibited paths DATA_BOUNDARIES exists to protect. That
# is a broader exposure than the narrow violation it would have fixed.
# TCC cannot be granted programmatically (tccutil only resets; the TCC
# databases are SIP-protected; PPPC profiles require MDM, and this host is
# not enrolled), so there is no scoped automated alternative.
#
# ⚠️ ACCEPTED WEAKNESS: backups now live on the same disk as the database
# they protect. This survives database corruption, a bad migration, or a
# dropped table — it does NOT survive disk failure or loss of the machine.
# An off-device copy is an open item (ADR-046 F1 follow-up). The dump is
# small (~1-2 MB gzipped from a 10 MB database), so this is cheap to add;
# any network destination must first clear the ADR-030 egress whitelist.
#
# Dumps are gitignored (backups/, *.sql.gz). Never commit them.
BACKUP_ROOT="$HOME/openclaw/backups"
BACKUP_DIR="$BACKUP_ROOT/dumps"
LOG_DIR="$BACKUP_ROOT/logs"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
DATESTAMP="$(date +%Y%m%d)"
DUMP_FILE="$BACKUP_DIR/openclaw_${TIMESTAMP}.sql.gz"
LOG_FILE="$LOG_DIR/backup_${DATESTAMP}.log"

# ── Secret / config lookup ───────────────────────────────────────────
# Bot token: stored in macOS Keychain per A1 (Entry #008).
# Operator chat id: not a secret — read from .env per existing telegram_bot.py
# convention (OPERATOR_TELEGRAM_ID). Verified via dump-keychain — only 6
# secrets are in Keychain and none is the operator id.

SERVICE_BOT_TOKEN="TELEGRAM_TOKEN_ROUTER"
ENV_FILE="$HOME/openclaw/.env"

keychain_get() {
  # $1 = service name; returns stdout = secret, or empty if not found
  /usr/bin/security find-generic-password -a "openclaw" -s "$1" -w 2>/dev/null
}

env_get() {
  # $1 = variable name; returns the rhs of VAR=value in .env, or empty
  # Tolerates lines with or without quotes around the value.
  if [ ! -f "$ENV_FILE" ]; then
    return 0
  fi
  /usr/bin/grep -E "^${1}=" "$ENV_FILE" 2>/dev/null \
    | /usr/bin/head -n 1 \
    | /usr/bin/sed -E "s/^${1}=//; s/^[\"']//; s/[\"']\$//"
}

# ── Logging ──────────────────────────────────────────────────────────
log() {
  # Append to today's log file with ISO 8601 timestamp.
  # If log dir is unreachable, fall back to stderr so cron mail captures it.
  local msg="[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"
  if [ -d "$LOG_DIR" ]; then
    echo "$msg" >> "$LOG_FILE"
  fi
  echo "$msg" >&2
}

# ── Telegram alert (failure path only) ───────────────────────────────
send_telegram_alert() {
  local subject="$1"
  local detail="$2"

  local bot_token
  bot_token="$(keychain_get "$SERVICE_BOT_TOKEN")"
  local chat_id
  chat_id="$(env_get "OPERATOR_TELEGRAM_ID")"

  if [ -z "$bot_token" ]; then
    log "ALERT_SKIPPED: Keychain returned empty for service=$SERVICE_BOT_TOKEN. Detail: $detail"
    return 1
  fi
  if [ -z "$chat_id" ]; then
    log "ALERT_SKIPPED: .env returned empty for OPERATOR_TELEGRAM_ID. Detail: $detail"
    return 1
  fi

  local hostname
  hostname="$(/bin/hostname -s)"
  local now_utc
  now_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  local payload
  payload="$(/usr/bin/printf '%s\n%s\n\n%s\n%s\n%s' \
    "🚨 BACKUP FAILURE — OpenClaw" \
    "Time: $now_utc  |  Host: $hostname" \
    "Stage: $subject" \
    "Detail: $detail" \
    "See $LOG_FILE for full log.")"

  # Telegram bot API call. -m 30 = 30 second timeout. Curl exit is captured
  # but the script continues — alert failure must not mask backup failure.
  /usr/bin/curl -s -m 30 \
    -d "chat_id=${chat_id}" \
    --data-urlencode "text=${payload}" \
    "https://api.telegram.org/bot${bot_token}/sendMessage" \
    > /dev/null 2>&1
  local rc=$?
  if [ $rc -eq 0 ]; then
    log "ALERT_SENT: $subject"
  else
    log "ALERT_CURL_FAILED: rc=$rc — subject=$subject"
  fi
  return $rc
}

# ── Preflight: directories exist (create if missing) ─────────────────
/bin/mkdir -p "$BACKUP_DIR" "$LOG_DIR"
if [ ! -d "$BACKUP_DIR" ] || [ ! -d "$LOG_DIR" ]; then
  log "FATAL: backup or log directory not creatable: $BACKUP_DIR | $LOG_DIR"
  send_telegram_alert "directory_unreachable" "Could not create or access $BACKUP_DIR"
  exit 3
fi

log "BACKUP_START: target=$DUMP_FILE"

# ── Preflight: postgres container running ────────────────────────────
if ! /usr/local/bin/docker ps --format '{{.Names}}' 2>/dev/null | /usr/bin/grep -q '^openclaw_postgres$'; then
  log "FATAL: openclaw_postgres container not running"
  send_telegram_alert "postgres_down" "openclaw_postgres container is not in docker ps. Backup skipped."
  exit 4
fi

# ── pg_dump with gzip compression ────────────────────────────────────
# -Z 9 = maximum gzip compression. For an 80KB plaintext dump the difference
# is negligible; for a 500MB future dump it's the difference between 500MB
# and ~80MB on disk. No downside.
#
# We pipe through to capture the gzipped output to a file. The pipefail option
# is set so that a pg_dump failure surfaces even though gzip would have exited 0.
set -o pipefail
/usr/local/bin/docker exec openclaw_postgres pg_dump -U openclaw -d openclaw -Z 9 > "$DUMP_FILE" 2>>"$LOG_FILE"
DUMP_RC=$?
set +o pipefail

if [ $DUMP_RC -ne 0 ]; then
  log "FATAL: pg_dump exited rc=$DUMP_RC"
  /bin/rm -f "$DUMP_FILE"  # remove the partial file
  send_telegram_alert "pg_dump_failed" "pg_dump exited rc=$DUMP_RC. Backup aborted, partial file removed."
  exit 2
fi

# ── Verify the dump is non-empty ─────────────────────────────────────
DUMP_SIZE=$(/usr/bin/stat -f %z "$DUMP_FILE" 2>/dev/null || echo 0)
if [ "$DUMP_SIZE" -lt 100 ]; then
  log "FATAL: dump file size $DUMP_SIZE bytes — suspiciously small"
  send_telegram_alert "pg_dump_empty" "Dump file is only $DUMP_SIZE bytes. Backup aborted."
  /bin/rm -f "$DUMP_FILE"
  exit 2
fi

log "BACKUP_OK: $DUMP_FILE  size=${DUMP_SIZE}B"

# ── 30-day retention per ADR-031 §7 ──────────────────────────────────
# Find any .sql.gz files older than 30 days in the interim folder and delete.
DELETED_COUNT=$(/usr/bin/find "$BACKUP_DIR" -type f -name 'openclaw_*.sql.gz' -mtime +30 -print -delete 2>/dev/null | /usr/bin/wc -l | /usr/bin/tr -d ' ')
if [ "$DELETED_COUNT" -gt 0 ]; then
  log "RETENTION: deleted $DELETED_COUNT file(s) older than 30 days"
fi

# Also prune old log files (90 days per ADR-019 spec — older than 90)
LOG_DELETED=$(/usr/bin/find "$LOG_DIR" -type f -name 'backup_*.log' -mtime +90 -print -delete 2>/dev/null | /usr/bin/wc -l | /usr/bin/tr -d ' ')
if [ "$LOG_DELETED" -gt 0 ]; then
  log "RETENTION: deleted $LOG_DELETED log file(s) older than 90 days"
fi

# ── Folder size check — Telegram alert if total > 5GB (one-time per cross) ──
# ADR-019 specifies this. We use a marker file to keep it one-time per crossing.
TOTAL_BYTES=$(/usr/bin/find "$BACKUP_DIR" -type f -name '*.sql.gz' -exec /usr/bin/stat -f %z {} \; 2>/dev/null | /usr/bin/awk '{s+=$1} END {print s+0}')
SIZE_THRESHOLD=$((5 * 1024 * 1024 * 1024))  # 5 GB in bytes
MARKER="$LOG_DIR/.size_5gb_alerted"
if [ "$TOTAL_BYTES" -gt "$SIZE_THRESHOLD" ] && [ ! -f "$MARKER" ]; then
  send_telegram_alert "size_threshold" "Backup folder exceeds 5GB: ${TOTAL_BYTES} bytes total."
  /usr/bin/touch "$MARKER"
  log "SIZE_ALERT: folder crossed 5GB threshold, marker set"
elif [ "$TOTAL_BYTES" -lt "$SIZE_THRESHOLD" ] && [ -f "$MARKER" ]; then
  # Folder dropped back below threshold — reset marker for future crossings
  /bin/rm -f "$MARKER"
  log "SIZE_ALERT: folder dropped below 5GB, marker cleared"
fi

log "BACKUP_COMPLETE: total_folder_size=${TOTAL_BYTES}B"

exit 0
