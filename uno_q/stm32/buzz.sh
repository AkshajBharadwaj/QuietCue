#!/usr/bin/env bash
# QuietCue haptic test helper. Run this ON the Uno Q:
#
#   ./buzz.sh              # safe status check; does not buzz
#   ./buzz.sh two_short    # bounded two-pulse motor test
#
# The script finds the running QuietCue App Lab container automatically. Set
# QUIETCUE_HAPTICS_CONTAINER only when more than one matching container exists.
set -euo pipefail

readonly COMMAND="${1:-status}"

usage() {
  cat <<'EOF'
Usage: ./buzz.sh [command]

Commands:
  status       Firmware, Bridge health, and motor-pin status (default)
  two_short    Two bounded short pulses
  long_pulse   One bounded long pulse
  urgent       Repeat the urgent pattern until button, stop, or 30 s timeout
  stop         Stop the active haptic pattern
  pin          Read the physical motor-pin level
  on           UNSAFE bench diagnostic: hold the raw motor pin high
  off          Turn the raw motor pin off
  help         Show this help

Optional environment override:
  QUIETCUE_HAPTICS_CONTAINER=<container-name> ./buzz.sh status
EOF
}

find_haptics_container() {
  if [[ -n "${QUIETCUE_HAPTICS_CONTAINER:-}" ]]; then
    printf '%s\n' "$QUIETCUE_HAPTICS_CONTAINER"
    return
  fi

  local candidate
  local -a matches=()
  while IFS= read -r candidate; do
    case "$candidate" in
      quietcue-haptics-main-1)
        printf '%s\n' "$candidate"
        return
        ;;
      *quietcue*haptics*main*)
        matches+=("$candidate")
        ;;
    esac
  done < <(docker ps --format '{{.Names}}')

  if (( ${#matches[@]} == 1 )); then
    printf '%s\n' "${matches[0]}"
    return
  fi
  if (( ${#matches[@]} == 0 )); then
    echo "ERROR: no running QuietCue haptics App Lab container was found." >&2
    echo "Start the QuietCue Haptics app in Arduino App Lab, then retry." >&2
  else
    echo "ERROR: multiple QuietCue haptics containers are running:" >&2
    printf '  %s\n' "${matches[@]}" >&2
    echo "Set QUIETCUE_HAPTICS_CONTAINER to the container you want." >&2
  fi
  return 1
}

case "$COMMAND" in
  help|-h|--help)
    usage
    exit 0
    ;;
  on)
    echo "WARNING: raw 'on' has no automatic timeout; run './buzz.sh off' immediately after the bench check." >&2
    bridge_expression='print(Bridge.call("set_motor_raw", True, timeout=8))'
    ;;
  off)
    bridge_expression='print(Bridge.call("set_motor_raw", False, timeout=8))'
    ;;
  pin)
    bridge_expression='print("motor_pin_high:", Bridge.call("get_motor_pin", timeout=8))'
    ;;
  two_short)
    bridge_expression='print(Bridge.call("play_haptic", "two_short", 255, 1, timeout=8))'
    ;;
  long_pulse)
    bridge_expression='print(Bridge.call("play_haptic", "long_pulse", 255, 1, timeout=8))'
    ;;
  urgent)
    bridge_expression='print(Bridge.call("play_haptic", "urgent_repeat", 255, 0, timeout=8))'
    ;;
  stop)
    bridge_expression='print(Bridge.call("stop_haptic", timeout=8))'
    ;;
  status)
    bridge_expression='print(Bridge.call("get_firmware_version", timeout=8)); print(Bridge.call("health_check", timeout=8)); print("motor_pin_high:", Bridge.call("get_motor_pin", timeout=8))'
    ;;
  *)
    echo "ERROR: unknown command: $COMMAND" >&2
    usage >&2
    exit 64
    ;;
esac

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is unavailable. Run this script on the Uno Q Linux side." >&2
  exit 127
fi

container="$(find_haptics_container)"
readonly container
printf 'from arduino.app_utils import Bridge\n%s\n' "$bridge_expression" | \
  docker exec -i "$container" python -
