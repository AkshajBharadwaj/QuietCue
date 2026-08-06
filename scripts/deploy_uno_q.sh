#!/usr/bin/env bash
# Deploy the latest QuietCue code to the Uno Q and (re)start the microphone
# client. Two ways to run it:
#
#   From the development machine (pushes over SSH, then runs itself remotely):
#     ./scripts/deploy_uno_q.sh arduino@<uno-q-tailscale-ip>
#     UNO_Q_HOST=arduino@<ip> ./scripts/deploy_uno_q.sh
#
#   Directly on the board:
#     ./scripts/deploy_uno_q.sh --local
#
# Client configuration comes from environment variables on the BOARD
# (put them in ~/.quietcue_env, which this script sources if present):
#   QUIETCUE_HUB            hub endpoint as HOST:PORT (e.g. 100.x.y.z:8765)
#   QUIETCUE_PAIRING_TOKEN  shared development token (same as the hub)
#   QUIETCUE_ALSA_DEVICE    ALSA capture device (default plughw:CARD=Microphone,DEV=0)
#
# GitHub is the source of truth: this script only ever `git pull`s the board
# clone. Never edit code directly on the Uno Q.
set -euo pipefail

PROJECT_DIR="${QUIETCUE_PROJECT_DIR:-$HOME/projects/QuietCue}"

if [ "${1:-}" != "--local" ]; then
    TARGET="${1:-${UNO_Q_HOST:-}}"
    if [ -z "$TARGET" ]; then
        echo "Usage: $0 <user@board-host> | --local" >&2
        echo "   or: UNO_Q_HOST=user@board-host $0" >&2
        exit 1
    fi
    echo "Deploying to $TARGET ..."
    # shellcheck disable=SC2029
    ssh "$TARGET" "cd ~/projects/QuietCue && git pull --ff-only && ./scripts/deploy_uno_q.sh --local"
    exit 0
fi

# ----- board-side deployment ----------------------------------------------------
cd "$PROJECT_DIR"

if [ -f "$HOME/.quietcue_env" ]; then
    # shellcheck disable=SC1091
    set -a; . "$HOME/.quietcue_env"; set +a
fi

echo "== QuietCue board deploy: $(git rev-parse --short HEAD) =="

# Stop any running client before starting a fresh one.
pkill -f 'uno_q.linux.transport.hub_client' 2>/dev/null && echo "Stopped previous client." || true
sleep 1

if [ -z "${QUIETCUE_HUB:-}" ]; then
    cat >&2 <<'EOF'
QUIETCUE_HUB is not set (expected HOST:PORT of the inference hub), so the
client was NOT started automatically. To configure, create ~/.quietcue_env:

    QUIETCUE_HUB=<hub-host>:8765
    QUIETCUE_PAIRING_TOKEN=<shared-development-token>
    QUIETCUE_ALSA_DEVICE=plughw:CARD=Microphone,DEV=0

then re-run: ./scripts/deploy_uno_q.sh --local
EOF
    exit 0
fi

if [ -z "${QUIETCUE_PAIRING_TOKEN:-}" ]; then
    echo "WARNING: QUIETCUE_PAIRING_TOKEN is not set; connecting without a token." >&2
fi

ALSA_DEVICE="${QUIETCUE_ALSA_DEVICE:-plughw:CARD=Microphone,DEV=0}"
LOG_FILE="$HOME/quietcue-client.log"

echo "Starting microphone client -> hub $QUIETCUE_HUB (device $ALSA_DEVICE)"
nohup python3 -m uno_q.linux.transport.hub_client \
    --microphone \
    --input-device "$ALSA_DEVICE" \
    --pc "$QUIETCUE_HUB" \
    --pairing-token "${QUIETCUE_PAIRING_TOKEN:-}" \
    --compact \
    >"$LOG_FILE" 2>&1 &

sleep 2
if pgrep -f 'uno_q.linux.transport.hub_client' >/dev/null; then
    echo "Client running. Logs: tail -f $LOG_FILE"
else
    echo "ERROR: client exited immediately. Last log lines:" >&2
    tail -n 20 "$LOG_FILE" >&2 || true
    exit 1
fi
