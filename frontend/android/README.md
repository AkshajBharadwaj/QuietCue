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

The dashboard currently shows the Snapdragon PC and Uno Q as disconnected. Live
status, event history, profile synchronization, and haptic preview will be added
with the backend API; local profile editing already works without that connection.

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

No microphone or network permission is requested in this first slice. Audio
capture remains on the Uno Q as required by the QuietCue architecture.
