# QuietCue Android companion

This app manages alert profiles locally and can also act as a connected inference
hub. The Uno Q streams microphone audio to either this phone or a computer; the
selected hub classifies it and returns compact alert commands for the Uno Q to
deliver to the STM32 haptic firmware.

## Implemented

- Home, Work / School, Driving / Transit, Sleep / Night, and Emergency profiles.
- Custom profile creation and profile duplication.
- Persistent active-profile selection and profile settings through DataStore.
- Per-sound enablement, confidence threshold, priority, haptic pattern, haptic
  strength, acknowledgement, and repeat cooldown.
- A touch-driven vibration creator: hold for motor-on time, release for pauses,
  preview the result on the phone, and save a bounded one-to-six-pulse pattern
  to any sound rule.
- Quiet hours with an unconditional emergency bypass.
- Name and phrase triggers.
- Encrypted global speech settings, per-profile speech overrides, fuzzy name
  matching, and lazy on-phone Whisper ONNX transcription on a separate worker.
- Optional activity and location labels for future automatic profile activation.
- Built-in profile reset and custom profile deletion.
- Local validation and unit tests for defaults, times, and persistence encoding.
- Local hub status, latest event, confidence, latency, backend profile,
  hardware-confirmed haptic output, and a Stop vibration control on the dashboard.
- System notifications for newly detected alerts from the sticky background
  service, including a Stop vibration action for active emergency patterns.
- A constrained local profile assistant that turns a situation description into
  a complete draft for explicit user review.
- One-tap custom sound teaching through the live Uno Q microphone: a guided
  ten-second session automatically extracts 3–30 repeated events, rejects
  speech-dominated chunks, calibrates room background, and discards raw audio.
- Active-profile and enrolled-fingerprint synchronization to the local hub.
- A foreground TCP inference service on port `8765` using the checked-in quantized
  W8A8 YAMNet ONNX model and ONNX Runtime for Android.
- The same `QC01` framed PCM16 protocol as the computer hub, including handshake,
  heartbeats, profile decisions, alert commands, and haptic delivery results.
- On-device 16 kHz YAMNet feature extraction and environmental-event mapping for
  fire alarms, sirens, horns, doorbells/knocks, crying babies, timers, and phones.
- A Smart Places tab with private on-phone place boundaries, Android geofence
  arrival/departure events, ask-first profile suggestions, opt-in automatic
  switching, return-to-previous-profile behavior, and two-hour manual overrides.
- A permission-free hackathon place simulator for deterministic arrival and
  departure demonstrations without physically moving the phone.

The phone inference service starts when the app opens and remains visible as a
foreground notification. The dashboard's **Inference device** card shows whether
the PC or Samsung is processing audio and switches the live stream without
restarting the Uno Q. It also shows the latest Samsung inference latency and polls the
computer development backend at `http://127.0.0.1:8787/api/state` when available.
Full event history remains future work; local profile editing,
profile drafting, and enrollment storage continue to work without a backend
connection. Recognition of an enrolled sound requires the hub connection.

## Requirements

- Android Studio with JDK 17 or newer.
- Android SDK Platform 37 and Build Tools 36.0.0 or newer.
- An Android device or emulator running Android 8.0 (API 26) or newer.

The project uses Android Gradle Plugin 9.3.1, Gradle 9.6.1, Kotlin 2.3.21, and the
stable Compose BOM `2026.06.00`.

## Build and test

Open `frontend/android` in Android Studio, or run:

```bash
cd frontend/android
./gradlew testDebugUnitTest
./gradlew assembleDebug
```

Install a debug build on a connected device with:

```bash
./gradlew installDebug
```

To create a personal vibration, open **Profiles**, edit a profile, expand a
sound, and choose **Custom** or **Create touch pattern** under Haptic pattern.
Recorded patterns are validated on the phone, hub, and STM32 before they can
reach the motor.

## Use the Samsung as the inference hub

For the normal connected demo, attach the Samsung over USB and run
`scripts/run_demo.sh --live`. The launcher forwards the private phone inference
port to the PC hub and the **PC** and **Samsung** buttons become available under
System status. The Uno Q keeps one stable connection to the PC hub; when Samsung
is selected the hub forwards each audio frame to the phone and returns the phone's
alert decision. If the phone disconnects, the PC handles audio until it is back.

The PC and Samsung use the same quantized W8A8 YAMNet model and AudioSet labels,
but not the same runtime: the PC uses the Python/NumPy frontend with ONNX Runtime
(and can use an available NPU), while Android uses the Kotlin frontend and ONNX
Runtime CPU. Their confidence scores and latency can therefore differ. The PC
uses Faster-Whisper for enabled speech rules; Samsung uses the staged Whisper
ONNX implementation.

For a phone-only network setup without the PC forwarding hub, put the phone and
Uno Q on the same trusted Wi-Fi network, open QuietCue once, and run on the Uno Q,
replacing `PHONE_IP` with the phone's Wi-Fi address:

```bash
python3 -u -m uno_q.linux.transport.hub_client \
  --microphone \
  --input-device plughw:CARD=Microphone,DEV=0 \
  --phone PHONE_IP:8765 \
  --preference samsung_phone \
  --haptics \
  --compact
```

Configure both endpoints to keep the computer as an automatic fallback:

```bash
python3 -u -m uno_q.linux.transport.hub_client \
  --microphone \
  --phone PHONE_IP:8765 \
  --pc COMPUTER_IP:8765 \
  --preference auto \
  --haptics \
  --compact
```

The phone performs quantized environmental-sound inference on CPU. It can also
run the staged Whisper ONNX encoder/decoder locally when speech is enabled and a
configured phrase is available; the model is loaded lazily and decoding never
blocks environmental inference. Model weights are not committed. Follow
[`../../docs/WHISPER_ONNX.md`](../../docs/WHISPER_ONNX.md) to validate and stage
the Tiny or Base assets.
The pairing token is optional during development, so port `8765` should only be
exposed on a trusted LAN or private overlay network.

For the local development state feed on a physical phone or emulator, forward the
backend port before opening the app:

```bash
adb reverse tcp:8787 tcp:8787
```

The app requests network permission for local metadata/profile synchronization and
the TCP inference listener. Custom-sound teaching uses the live Uno Q microphone;
phone microphone permission is reserved for explicit on-phone identity/name tools.
Continuous monitoring audio remains on the Uno Q. See
[`../../docs/NO_HARDWARE_DEMO.md`](../../docs/NO_HARDWARE_DEMO.md) for the complete
microphone-free workflow.

Location permission is requested only when the user saves or enables a Smart
Place. Place coordinates remain in the phone's DataStore and are never included
in hub profile synchronization. Full background arrival/departure suggestions
require precise location plus **Allow all the time** access; the rest of QuietCue
continues to work if either permission is declined. See
[`../../docs/SMART_PROFILE_SUGGESTIONS.md`](../../docs/SMART_PROFILE_SUGGESTIONS.md).

The enrollment matcher is currently a provisional local spectral fingerprint. It
is suitable for validating the enrollment product flow, not as a sole detector for
safety-critical sounds. It will be replaced with a measured learned embedding
model before production use.
