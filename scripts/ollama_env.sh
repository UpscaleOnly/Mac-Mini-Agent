#!/bin/bash
# ollama_env.sh — Ollama server settings, applied at login (ADR-047 §6, §9).
#
# Run by ~/Library/LaunchAgents/com.openclaw.ollama-env.plist (template:
# scripts/com.openclaw.ollama-env.plist.template). Ollama.app reads its server
# settings from the launchd user environment when it starts, so this sets them
# there and then restarts Ollama.app, which may already have launched at login
# without them.
#
# Scope (DATA_BOUNDARIES v2.1 §1): launchctl env changes are limited to
# variables named OLLAMA_*. Nothing else is read or written.
#
# Verify after a run: the server logs its effective settings at startup —
#   grep 'server config' ~/.ollama/logs/server.log | tail -1
#
# Deliberately NOT set here (ADR-047 §5): OLLAMA_FLASH_ATTENTION and
# OLLAMA_KV_CACHE_TYPE. They are added only with the 16K-context measurement.

set -u

SETTINGS=(
    "OLLAMA_MAX_LOADED_MODELS=1"   # one model in memory at a time
    "OLLAMA_NUM_PARALLEL=1"        # one request slot; parallel slots multiply KV-cache memory
)

for kv in "${SETTINGS[@]}"; do
    /bin/launchctl setenv "${kv%%=*}" "${kv#*=}"
done
echo "$(date '+%F %T') launchd env set: ${SETTINGS[*]}"

# Restart Ollama.app so its server reads the settings. A plain SIGTERM, not an
# AppleScript "quit": from a LaunchAgent, AppleScript needs a TCC Automation
# grant and failed with -128 on first install (Entry #048). No grant is taken.
if /usr/bin/pgrep -xq Ollama; then
    /usr/bin/pkill -TERM -x Ollama
    for _ in $(seq 1 20); do
        /usr/bin/pgrep -xq Ollama || break
        sleep 1
    done
fi
/usr/bin/open -a Ollama
echo "$(date '+%F %T') Ollama.app (re)started"
