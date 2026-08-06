#!/usr/bin/env bash
# Stable Uno Q runtime entrypoint used by the user systemd service.
set -euo pipefail

readonly PROJECT_DIR="${QUIETCUE_PROJECT_DIR:-$HOME/projects/QuietCue}"
readonly ENV_FILE="${QUIETCUE_ENV_FILE:-$HOME/.quietcue_env}"
readonly APP_DIR="${QUIETCUE_HAPTICS_APP_DIR:-$HOME/ArduinoApps/quietcue-haptics}"

if [[ -f "$ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    set -a; source "$ENV_FILE"; set +a
fi

readonly PC_HUB="${QUIETCUE_PC_HUB:-${QUIETCUE_HUB:-}}"
readonly PHONE_HUB="${QUIETCUE_PHONE_HUB:-}"

if [[ -z "$PC_HUB" && -z "$PHONE_HUB" ]]; then
    echo "ERROR: configure QUIETCUE_PC_HUB/QUIETCUE_PHONE_HUB in $ENV_FILE" >&2
    exit 78
fi

if [[ ! -d "$APP_DIR" ]]; then
    echo "ERROR: QuietCue App Lab app not found at $APP_DIR" >&2
    exit 78
fi

if ! docker ps --format '{{.Names}}' | grep -qx 'quietcue-haptics-main-1'; then
    echo "Starting QuietCue Haptics App Lab app..."
    arduino-app-cli app start "$APP_DIR"
fi

for _ in {1..30}; do
    if docker ps --format '{{.Names}}' | grep -qx 'quietcue-haptics-main-1'; then
        break
    fi
    sleep 1
done

if ! docker ps --format '{{.Names}}' | grep -qx 'quietcue-haptics-main-1'; then
    echo "ERROR: QuietCue Haptics App Lab container did not become ready" >&2
    exit 1
fi

cd "$PROJECT_DIR"

readonly ALSA_DEVICE="${QUIETCUE_ALSA_DEVICE:-plughw:CARD=Microphone,DEV=0}"
readonly DEVICE_ID="${QUIETCUE_DEVICE_ID:-uno-q-dev}"

client_args=(
    --microphone
    --input-device "$ALSA_DEVICE"
    --device-id "$DEVICE_ID"
    --haptics
    --compact
)
if [[ -n "$PC_HUB" ]]; then
    client_args+=(--pc "$PC_HUB")
fi
if [[ -n "$PHONE_HUB" ]]; then
    client_args+=(--phone "$PHONE_HUB")
fi

echo "Starting QuietCue: microphone $ALSA_DEVICE, inference hub PC=${PC_HUB:-none}, phone=${PHONE_HUB:-none}, haptics enabled"
exec python3 -u -m uno_q.linux.transport.hub_client "${client_args[@]}"
