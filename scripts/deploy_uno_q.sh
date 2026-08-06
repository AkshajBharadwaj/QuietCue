#!/usr/bin/env bash
# Deploy the latest QuietCue code, App Lab firmware, and restartable runtime to
# the Uno Q. Two ways to run it:
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
# GitHub is the source of truth. The board clone is deployed into App Lab and a
# user systemd service; no long-running process is managed with nohup.
set -euo pipefail

PROJECT_DIR="${QUIETCUE_PROJECT_DIR:-$HOME/projects/QuietCue}"
APP_DIR="${QUIETCUE_HAPTICS_APP_DIR:-$HOME/ArduinoApps/quietcue-haptics}"
SERVICE_NAME="quietcue-client.service"

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

if [ ! -d "$APP_DIR" ]; then
    echo "ERROR: QuietCue App Lab app is not installed at $APP_DIR" >&2
    echo "Import uno_q/stm32/haptics once in Arduino App Lab, then retry." >&2
    exit 1
fi

echo "Synchronizing the tracked App Lab app..."
install -m 0644 uno_q/stm32/haptics/app.yaml "$APP_DIR/app.yaml"
install -d "$APP_DIR/python" "$APP_DIR/sketch"
install -m 0644 uno_q/stm32/haptics/python/main.py "$APP_DIR/python/main.py"
install -m 0644 uno_q/stm32/haptics/sketch/sketch.ino "$APP_DIR/sketch/sketch.ino"
install -m 0644 uno_q/stm32/haptics/sketch/sketch.yaml "$APP_DIR/sketch/sketch.yaml"

echo "Restarting App Lab to compile/flash the tracked firmware..."
arduino-app-cli app restart "$APP_DIR"

install -d "$HOME/.config/systemd/user"
install -m 0644 \
    uno_q/linux/systemd/quietcue-client.service \
    "$HOME/.config/systemd/user/$SERVICE_NAME"
systemctl --user daemon-reload
systemctl --user enable "$SERVICE_NAME" >/dev/null

if [ -z "${QUIETCUE_HUB:-}" ]; then
    cat >&2 <<'EOF'
QUIETCUE_HUB is not set (expected HOST:PORT of the inference hub), so the
client was NOT started automatically. To configure, create ~/.quietcue_env:

    QUIETCUE_HUB=<hub-host>:8765
    QUIETCUE_PAIRING_TOKEN=<shared-development-token>
    QUIETCUE_ALSA_DEVICE=plughw:CARD=Microphone,DEV=0

then re-run: ./scripts/deploy_uno_q.sh --local
EOF
    systemctl --user stop "$SERVICE_NAME" 2>/dev/null || true
    systemctl --user reset-failed "$SERVICE_NAME" 2>/dev/null || true
    exit 0
fi

if [ -z "${QUIETCUE_PAIRING_TOKEN:-}" ]; then
    echo "WARNING: QUIETCUE_PAIRING_TOKEN is not set; connecting without a token." >&2
fi

chmod +x scripts/run_uno_q_client.sh uno_q/stm32/buzz.sh
systemctl --user restart "$SERVICE_NAME"
sleep 3

echo
echo "== Runtime status =="
systemctl --user --no-pager --full status "$SERVICE_NAME" || true
echo
echo "Logs: journalctl --user -u $SERVICE_NAME -f"
echo "Haptic status: cd $PROJECT_DIR/uno_q/stm32 && ./buzz.sh status"
