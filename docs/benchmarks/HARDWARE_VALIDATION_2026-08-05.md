# Uno Q haptic integration validation — 2026-08-05

This report records commands actually executed against the live Arduino Uno Q
(`cute`) over Tailscale. The environmental classifier was the deterministic
demo classifier; this validates transport, profile decisions, Bridge RPC, and
STM32 command execution, not real-world acoustic accuracy.

## Firmware and App Lab

- Uno Q core: `arduino:zephyr` 0.90.0.
- RouterBridge: 0.4.3.
- Firmware: `quietcue-haptics/0.2.0`.
- Sketch compiled at 88,032 bytes flash (11%) and 31,550 bytes RAM (12%).
- Normal App Lab startup called only `get_firmware_version` and `health_check`;
  `patterns_played` remained zero, confirming startup did not actuate the motor.

## Real Bridge adapter

The host-side `AppLabBridgeHapticTransport` was run against the live App Lab
container.

| Measurement | Result |
|---|---:|
| One-time persistent-worker warm-up | 1,477.2 ms |
| Warm `get_firmware_version` RPC | 10.5 ms |
| Warm `get_button_state` RPC | 8.3 ms |
| Warm `health_check` RPC | 17.4 ms |

A bounded `short_pulse` dispatch returned `delivered: true`. Firmware health
then reported `patterns_played: 1`, `pattern: none`, and the physical motor pin
low. Remote telemetry verifies the pin/pattern state and RPC result; a person
beside the board must still confirm the tactile vibration itself.

## Full Wi-Fi alert loop

A 0.5-second generated doorbell WAV was replayed on the Uno Q through the real
TCP protocol to the development hub at `100.73.217.43:8765`, using the Home
profile and real haptics.

- Hub selection RTT: 95 ms.
- Detection: `doorbell_knock`, confidence 0.98.
- Profile result: attention / `long_pulse` / standard strength.
- Hub alert-command timestamp: `22:38:47.954` local development time.
- Hub hardware-result timestamp: `22:38:47.991`.
- Alert command → confirmed haptic result: **37 ms**.
- State API changed `simulated` from `true` to `false` and attached the device,
  pattern, and delivery timestamp.
- Firmware counter increased from 2 to 3, then returned to `pattern: none` with
  the motor pin low.

## Recovery and service lifecycle

The installed `quietcue-client.service` passed `systemd-analyze --user verify`,
was enabled successfully, and ran with the real persistent Bridge worker. With
the documented USB microphone disconnected, the client stayed alive and used
bounded reconnect delays of 1 s then 2 s rather than crashing. The service was
stopped after this test because `~/.quietcue_env` and a working microphone are
not currently present on the board.

## Automated validation

- Python: 40 tests passed, including Bridge worker reuse, delivery failure
  retry, reconnect behavior, hardware telemetry, and unconfigured-sound fallback.
- Android: the complete Gradle unit-test task completed successfully using the
  in-process Kotlin compiler.

## Remaining external prerequisite

Reconnect the USB condenser microphone (or identify a valid onboard capture
configuration), then create `~/.quietcue_env` and run
`./scripts/deploy_uno_q.sh --local`. No further motor-path code is required for
the live microphone demo.
