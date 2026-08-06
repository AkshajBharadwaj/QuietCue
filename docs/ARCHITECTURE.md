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
- edge analysis: loudness, VAD, tonal-alarm candidates
- chunked PCM16 transport, hub selection, pairing token
    |
    |  Wi-Fi / Tailscale, raw TCP, 16 kHz mono PCM16 in 20-1000 ms chunks
    v
Snapdragon X Elite hub    backend/
- environmental classifier (YAMNet baseline or demo simulator)
- gated Faster-Whisper speech path (name/phrase triggers)
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
| Snapdragon PC (hub) | classification, speech, profiles, prioritization, dashboard API, benchmarks | depend on cloud for alerts |
| Uno Q Linux | capture, edge candidates, transport, RPC to STM32 | heavy ML, dev tooling |
| STM32 | exact motor timing, ack button, LEDs | networking, ML |
| Android app | profile editing, enrollment, event history | be required for the core demo |

## Protocols

- **Audio up:** length-prefixed wire messages (`backend/communication/stream_protocol.py`).
  `edge_hello` (device id + pairing token) -> `hub_hello` -> repeated
  `audio_chunk` (sequence, captured_at_ms, sample_rate 16000, channels 1,
  `pcm_s16le` payload, edge_analysis, phrase_triggers) -> `detection_result`
  per chunk. Heartbeats supported.
- **Alerts down:** each `detection_result` carries decided alerts
  (`event`, `category`, `pattern`, `requires_ack`, confidence, profile).
- **State API:** HTTP on port 8787 (`/health`, `/api/state`, profile sync
  endpoint used by the Android app).
- **Haptic categories:** informational `two_short`, attention `long_pulse`,
  emergency `urgent_repeat` (repeats until acknowledged).

## Implementation status (2026-08-05)

| Component | Path | Status |
|---|---|---|
| Hub server, protocol, state API | `backend/app/`, `backend/communication/` | Done |
| Demo classifier + no-hardware loop | `backend/inference/demo_classifier.py`, `scripts/run_no_hardware_demo.py` | Done |
| YAMNet baseline classifier | `backend/inference/sound_classifier.py` | Done (baseline, not safety-certified) |
| Gated speech path (Faster-Whisper) | `backend/inference/speech.py` | Done |
| Profiles, quiet hours, enrollment, identity context | `backend/profiles/` | Done |
| Uno Q live microphone + edge analyzer | `uno_q/linux/audio_capture/` | Done (validated with USB condenser mic) |
| Uno Q transport + hub selection | `uno_q/linux/transport/` | Done |
| Android companion app | `frontend/android/` | Done (optional for demo) |
| STM32 haptic firmware + RPC server | `uno_q/stm32/` | In progress today |
| Linux-side RPC client (alert -> motor) | `uno_q/linux/rpc_client/` | In progress today |
| Converted/quantized models | `models/` | Being populated (QUAD INT8 lane) |
| QUAD benchmarks | `docs/benchmarks/` | Being populated |

Until the STM32 and RPC-client lanes land, the hub logs
`SIMULATED HAPTIC <pattern>` instead of driving the motor; the rest of the
loop is real.

## Design rules (from AGENTS.md)

- Wi-Fi for audio streaming; BLE only later for small commands.
- Safety-critical detection stays local; cloud AI (if any) is advisory only.
- Speech transcription is gated and never blocks environmental detection.
- Few haptic patterns: urgency lives in the pattern, the exact event lives in
  the app.
- Report both model latency and full user-perceived latency.
