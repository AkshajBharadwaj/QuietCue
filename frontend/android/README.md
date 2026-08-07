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
- Quiet hours with an unconditional emergency bypass.
- Name and phrase triggers.
- Optional activity and location labels for future automatic profile activation.
- Built-in profile reset and custom profile deletion.
- Local validation and unit tests for defaults, times, and persistence encoding.
- Local hub status, latest event, confidence, latency, backend profile,
  hardware-confirmed haptic output, and a Stop vibration control on the dashboard.
- System notifications for newly detected alerts while the app is running and
  notification permission is granted.
- A constrained local profile assistant that turns a situation description into
  a complete draft for explicit user review.
- Custom sound enrollment using three two-second examples, one background sample,
  and an acoustic fingerprint that discards raw audio immediately.
- Active-profile and enrolled-fingerprint synchronization to the local hub.
- A foreground TCP inference service on port `8765` using the checked-in quantized
  W8A8 YAMNet ONNX model and ONNX Runtime for Android.
- The same `QC01` framed PCM16 protocol as the computer hub, including handshake,
  heartbeats, profile decisions, alert commands, and haptic delivery results.
- On-device 16 kHz YAMNet feature extraction and environmental-event mapping for
  fire alarms, sirens, horns, doorbells/knocks, crying babies, timers, and phones.
- Sound Scout cards from the computer hub after three distinct high-confidence
  episodes of an unmapped label, with reviewed direct-to-profile, dismiss, and
  prefilled custom-enrollment actions.
- A Smart Places tab with private on-phone place boundaries, Android geofence
  arrival/departure events, ask-first profile suggestions, opt-in automatic
  switching, return-to-previous-profile behavior, and two-hour manual overrides.
- A permission-free hackathon place simulator for deterministic arrival and
  departure demonstrations without physically moving the phone.

The phone inference service starts when the app opens and remains visible as a
foreground notification. The dashboard shows whether the model is ready, whether
an Uno Q is connected, and the latest phone inference latency. It also polls the
computer development backend at `http://127.0.0.1:8787/api/state` when available.
Full event history and haptic preview remain future work; Sound Scout candidates,
local profile editing,
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

## Use the Samsung as the inference hub

Put the phone and Uno Q on the same trusted Wi-Fi network, open QuietCue once,
and confirm the dashboard says `Listening on TCP 8765 • onnx_cpu`. Then run on
the Uno Q, replacing `PHONE_IP` with the phone's Wi-Fi address:

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

The phone currently performs quantized environmental-sound inference on CPU.
Speech transcription and enrolled-sound matching remain computer-hub features.
The pairing token is optional during development, so port `8765` should only be
exposed on a trusted LAN or private overlay network.

For the local development state feed on a physical phone or emulator, forward the
backend port before opening the app:

```bash
adb reverse tcp:8787 tcp:8787
```

The app requests network permission for local metadata/profile synchronization and
the TCP inference listener, and microphone permission only while the user explicitly
records enrollment examples. Continuous monitoring audio remains on the Uno Q. See
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
