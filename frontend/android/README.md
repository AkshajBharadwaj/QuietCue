# QuietCue Android companion

This is the optional QuietCue companion app. It manages alert profiles locally and
does not sit in the safety-critical sound-to-haptic path.

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
- Read-only local hub status, latest event, confidence, latency, backend profile,
  and hardware-confirmed haptic output on the dashboard when a Uno Q is connected.
- A constrained local profile assistant that turns a situation description into
  a complete draft for explicit user review.
- Custom sound enrollment using three two-second examples, one background sample,
  and an acoustic fingerprint that discards raw audio immediately.
- Active-profile and enrolled-fingerprint synchronization to the local hub.

The dashboard polls the development backend at `http://127.0.0.1:8787/api/state`.
Full event history and haptic preview remain future work; local profile editing,
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

For the local development state feed on a physical phone or emulator, forward the
backend port before opening the app:

```bash
adb reverse tcp:8787 tcp:8787
```

The app requests network permission for local metadata/profile synchronization and
microphone permission only while the user explicitly records enrollment examples.
Continuous monitoring audio remains on the Uno Q in the final architecture. See
[`../../docs/NO_HARDWARE_DEMO.md`](../../docs/NO_HARDWARE_DEMO.md) for the complete
microphone-free workflow.

The enrollment matcher is currently a provisional local spectral fingerprint. It
is suitable for validating the enrollment product flow, not as a sole detector for
safety-critical sounds. It will be replaced with a measured learned embedding
model before production use.
