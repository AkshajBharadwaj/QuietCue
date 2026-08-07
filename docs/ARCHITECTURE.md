# QuietCue architecture

QuietCue turns important environmental sounds into clear haptic alerts for
deaf and hard-of-hearing users. Detection stays local; no cloud service sits
in the alert path.

## System diagram

```text
Environment
    |
    v
Microphone (USB/ALSA) on Arduino Uno Q
    |
    v
Uno Q Linux side          uno_q/linux/
- ALSA capture (arecord pipe, never written to disk)
- signal diagnostics: loudness and voice activity (not classification)
- chunked PCM16 transport, hub selection, pairing token
    |
    |  Wi-Fi / Tailscale, raw TCP, 16 kHz mono PCM16 in 20-1000 ms chunks
    v
Connected hub             backend/ or frontend/android/
- environmental classifier (computer or Samsung quantized ONNX)
- gated Faster-Whisper (computer) or Whisper ONNX (Samsung) speech path
- custom enrolled-sound matcher
- profile + quiet-hours decision engine
- alert state store + HTTP state API for the Android app
    |
    |  compact alert command (event, category, pattern, requires_ack)
    v
Uno Q Linux side  --Arduino RPC-->  STM32
                                    - deterministic motor timing
                                    - ack button, status LED
    |
    v
Haptic feedback (two_short / long_pulse / urgent_repeat)
```

## Device responsibilities

| Device | Owns | Must never do |
|---|---|---|
| Connected hub | classification, speech, profiles, prioritization, dashboard API | depend on cloud for alerts |
| Uno Q Linux | capture, signal diagnostics, transport, RPC to STM32 | classify environmental events or invent alerts while disconnected |
| STM32 | exact motor timing, ack button, LEDs | networking, ML |
| Android app / Samsung hub | profile editing, optional quantized environmental inference | capture the continuous monitoring stream with its own microphone |

## Protocols

- **Audio up:** length-prefixed wire messages (`backend/communication/stream_protocol.py`).
  `edge_hello` (device id + pairing token) -> `hub_hello` -> repeated
  `audio_chunk` (sequence, captured_at_ms, sample_rate 16000, channels 1,
  `pcm_s16le` payload, signal diagnostics, phrase_triggers) -> `detection_result`
  per chunk. Heartbeats supported.
- **Alerts down:** each `detection_result` carries decided alerts
  (`event`, `category`, `pattern`, `requires_ack`, confidence, profile).
- **State API:** HTTP on port 8787 (`/health`, `/api/state`, profile sync
  endpoint used by the Android app).
- **Haptic categories:** informational `short_pulse` or `two_short`, attention `long_pulse`,
  emergency `urgent_repeat` (repeats until acknowledged).
- **Hardware result:** the Uno Q sends `haptic_result` after dispatch so the
  hub records delivery, bridge health, and acknowledgement state.

## Implementation status (2026-08-06)

| Component | Path | Status |
|---|---|---|
| Hub server, protocol, state API | `backend/app/`, `backend/communication/` | Done |
| Demo classifier + no-hardware loop | `backend/inference/demo_classifier.py`, `scripts/run_no_hardware_demo.py` | Done |
| YAMNet baseline classifier | `backend/inference/sound_classifier.py` | Done (baseline, not safety-certified) |
| Gated speech path (Faster-Whisper) | `backend/inference/speech.py` | Done |
| Samsung speech path (Whisper ONNX) | `frontend/android/app/src/main/java/com/quietcue/app/phone/speech/` | Implemented and JVM-tested; model/phone latency validation pending |
| Profiles, quiet hours, enrollment, identity context | `backend/profiles/` | Done |
| Sound Scout observation + recurring-label discovery | `backend/telemetry/` | Done on computer hub; persisted metadata and reviewed label rules |
| Uno Q live microphone + signal diagnostics | `uno_q/linux/audio_capture/` | Done: USB mic validated; no event inference on board |
| Uno Q transport + hub selection | `uno_q/linux/transport/` | Done |
| Android companion app | `frontend/android/` | Done: profiles, private context, Sound Scout, and smart-place suggestions (optional for demo) |
| On-phone geofence context | `frontend/android/app/src/main/java/com/quietcue/app/location/` | Done: local-only place rules, arrival/departure suggestions, opt-in automation, and demo simulation |
| Samsung TCP inference hub | `frontend/android/app/src/main/java/com/quietcue/app/phone/` | Quantized YAMNet plus lazy Whisper ONNX on independent workers |
| STM32 haptic firmware + RPC server | `uno_q/stm32/` | Done; App Lab firmware 0.2.0 |
| Linux-side RPC client (alert -> motor) | `uno_q/linux/rpc_client/` | Done; real App Lab Bridge transport |
| Board restart/reconnect lifecycle | `scripts/run_uno_q_client.sh`, `uno_q/linux/systemd/` | Done |
| Converted/quantized models | `models/` | Done: W8A8 ONNX + 3.63 MB INT8 DLC checked in |
| QUAD benchmarks | `docs/benchmarks/` | Done for Snapdragon X Elite; not transferable to QRB2210 |

QUAD produced the checked-in INT8 DLC and W8A8 ONNX artifacts. They are retained
for capable Samsung/PC inference runtimes. Physical testing showed that the
original QRB2210 UNO Q exposes an audio DSP, not the HTP/CDSP target used by the
converted DLC; strict SNPE DSP execution reported no matching backend. The board
therefore streams audio and never claims accelerator inference.

Without `--haptics`, alerts remain pending/simulated. The managed Uno Q service
always enables haptics and reports the actual firmware result to the hub.

## Design rules (from AGENTS.md)

- Wi-Fi for audio streaming; BLE only later for small commands.
- Safety-critical detection stays local; cloud AI (if any) is advisory only.
- Speech transcription is gated and never blocks environmental detection.
- Recurring unmapped classifier labels are advisory discoveries and never trigger
  emergency behavior or retain raw audio.
- Few haptic patterns: urgency lives in the pattern, the exact event lives in
  the app.
- Report both model latency and full user-perceived latency.
