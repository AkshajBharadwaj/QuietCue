#!/bin/bash
# QuietCue haptic test helper. Run on the Uno Q:  ./buzz.sh <command>
# Commands: on | off | pin | two_short | long_pulse | urgent | stop | status
# Deployed copy lives at ~/buzz.sh on the board; canonical copy is
# uno_q/stm32/buzz.sh in the repository.
CMD="${1:-status}"

python_body() {
case "$CMD" in
  on)         echo 'print(Bridge.call("set_motor_raw", True, timeout=8))' ;;
  off)        echo 'print(Bridge.call("set_motor_raw", False, timeout=8))' ;;
  pin)        echo 'print("motor_pin_high:", Bridge.call("get_motor_pin", timeout=8))' ;;
  two_short)  echo 'print(Bridge.call("play_haptic", "two_short", 255, 1, timeout=8))' ;;
  long_pulse) echo 'print(Bridge.call("play_haptic", "long_pulse", 255, 1, timeout=8))' ;;
  urgent)     echo 'print(Bridge.call("play_haptic", "urgent_repeat", 255, 0, timeout=8))' ;;
  stop)       echo 'print(Bridge.call("stop_haptic", timeout=8))' ;;
  status)     echo 'print(Bridge.call("get_firmware_version", timeout=8)); print(Bridge.call("health_check", timeout=8)); print("motor_pin_high:", Bridge.call("get_motor_pin", timeout=8))' ;;
  *) echo "unknown command: $CMD" >&2; exit 1 ;;
esac
}

{ echo 'from arduino.app_utils import Bridge'; python_body; } | \
  docker exec -i quietcue-haptics-main-1 python -
