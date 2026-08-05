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
  and simulated haptic output on the dashboard.

The dashboard polls the development backend at `http://127.0.0.1:8787/api/state`.
Profile synchronization, full event history, and haptic preview remain future
work; local profile editing continues to work without a backend connection.

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

The app requests network permission only for this local metadata feed. It does not
capture audio; audio capture remains on the Uno Q in the final architecture. See
[`../../docs/NO_HARDWARE_DEMO.md`](../../docs/NO_HARDWARE_DEMO.md) for the complete
microphone-free workflow.
