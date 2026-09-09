# QuietCue for iPhone

A SwiftUI port of the Android companion app that also plays the wearable's
role: the iPhone microphone streams to the Mac hub and the iPhone's haptic
engine vibrates with the same patterns the Uno Q motor uses. Every tab from the
Android app is here: Home, Profiles (with the editor and touch-recorded
haptics), Places, and My context.

```
iPhone mic ──16 kHz PCM16 over TCP──▶ Mac hub (YAMNet ONNX + profile rules)
iPhone haptics ◀── detection_result alerts ─┘        │
iPhone dashboard ◀── GET /api/state, PUT profile ────┘
```

## Run it

1. On the Mac: `./scripts/run_ios_demo.sh`. It prints the Mac's Wi-Fi address.
   On first run it downloads the float YAMNet export (15 MB) via
   `scripts/fetch_models.sh`; the checked-in quantized model only produces a
   coarse ladder of confidences, which most profile thresholds cannot clear.
2. Open `frontend/ios/QuietCue.xcodeproj` in Xcode 26, select the `QuietCue`
   target, choose your personal team under *Signing & Capabilities*, plug in
   the iPhone, and press Run.
3. On the phone, enter the Mac's address in the **Mac hub** card on the Home
   tab and tap **Connect**. Allow microphone and local-network access.
4. Make a sound. The hub log shows the alert command; the phone buzzes and the
   Latest alert card shows event, confidence, latency, and delivery.

Both devices must be on the same Wi-Fi. Keep the app in the foreground while
demoing: iOS stops Core Haptics playback when an app is in the background,
although the microphone stream keeps running thanks to the audio background
mode.

## Develop without a phone

The iOS Simulator uses the Mac's microphone, so the whole loop runs locally:

```bash
./scripts/run_ios_demo.sh --classifier demo &      # tone classifier: 1 kHz = fire alarm
cd frontend/ios
xcodebuild -scheme QuietCue -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build
xcrun simctl boot "iPhone 17 Pro"; open -a Simulator
xcrun simctl install booted <DerivedData>/Build/Products/Debug-iphonesimulator/QuietCue.app
xcrun simctl privacy booted grant microphone com.quietcue.app.ios
SIMCTL_CHILD_QUIETCUE_HUB_HOST=127.0.0.1 xcrun simctl launch booted com.quietcue.app.ios
python3 scripts/generate_demo_audio.py alarm /tmp/fire.wav --duration 6 && afplay /tmp/fire.wav
```

Environment overrides read at launch: `QUIETCUE_HUB_HOST`,
`QUIETCUE_PAIRING_TOKEN`, and `QUIETCUE_SKIP_NOTIFICATION_PROMPT` (for
automated runs).

## Tests

```bash
cd frontend/ios
xcodebuild -scheme QuietCue -destination 'platform=iOS Simulator,name=iPhone 17 Pro' test -only-testing:QuietCueTests
```

`QuietCueTests` covers the wire framing, the edge analyzer, and the
profile-sync document. Setting `TEST_RUNNER_QUIETCUE_FIXTURE_DIR=<repo>/tests/fixtures`
regenerates `tests/fixtures/ios_profile_sync.json`, which
`tests/test_ios_profile_sync.py` then validates with the hub's real decoder.

`QuietCueUITests` contains a screenshot tour of every screen; set
`TEST_RUNNER_QUIETCUE_SHOT_DIR=<dir>` to run it and collect PNGs.

## Layout

| Folder | Contents |
|---|---|
| `QuietCue/Domain` | Profiles, sounds, memory bank, smart places, fingerprints, local text agent (ports of the Android domain) |
| `QuietCue/Edge` | Wire protocol, TCP client, microphone capture, edge analysis, haptic engine, alert dispatcher, session loop |
| `QuietCue/Data` | Local stores, hub status client, profile-sync codec, hub settings |
| `QuietCue/Location` | Core Location geofences and the smart-profile coordinator |
| `QuietCue/Speech` | On-device recognizer for name voice checks |
| `QuietCue/Notifications` | Local notifications with the acknowledge action |
| `QuietCue/UI` | Material-styled SwiftUI screens matching the Android app |
| `Support/Info.plist` | Permissions, background audio, local-network ATS exception |

The project file uses Xcode's synchronized folders, so new Swift files under
`QuietCue/` are picked up without editing the project. The hub itself needed no
changes.
