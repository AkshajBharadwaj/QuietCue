# No-hardware audio demo

This workflow tests QuietCue before the Uno Q microphone is available. It uses the
real audio packet format and network server, but replaces microphone capture and
ML inference with labeled WAV replay and a deterministic tone classifier.

It validates:

- 16 kHz mono PCM16 packetization in 500 ms chunks;
- edge metadata generation;
- binary TCP framing and hub negotiation;
- environmental event mapping;
- profile enablement, threshold, quiet-hours, and cooldown decisions;
- simulated haptic commands;
- metadata-only Android dashboard updates.

It does not validate microphone quality, real-world model accuracy, Wi-Fi behavior,
Uno Q timing, Arduino RPC, or a vibration motor.

## Quick terminal smoke test

From the repository root:

```bash
python3 scripts/run_no_hardware_demo.py --event fire_alarm --profile home
```

No third-party Python packages are required. The command starts a temporary demo
hub, generates a WAV, streams it, prints the detection and alert command, and then
stops the hub.

Supported synthetic events are `doorbell_knock`, `car_horn`, `fire_alarm`,
`siren`, `baby_crying`, `kitchen_timer`, and `phone_ringing`. Backend profiles are
`home`, `work`, `driving`, `sleep`, and `emergency`.

For example, Home deliberately suppresses a car horn while Driving turns it into
an emergency alert:

```bash
python3 scripts/run_no_hardware_demo.py --event car_horn --profile home
python3 scripts/run_no_hardware_demo.py --event car_horn --profile driving
```

## Show the alert on an attached Android phone

Build and install the current app:

```bash
cd frontend/android
./gradlew testDebugUnitTest assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
cd ../..
```

Forward the phone's loopback state port to the development computer:

```bash
adb reverse tcp:8787 tcp:8787
```

Keep the demo hub running in terminal 1:

```bash
python3 -m backend.app.hub_server --classifier demo --profile home
```

Generate and replay an event in terminal 2:

```bash
python3 scripts/generate_demo_audio.py fire_alarm /tmp/quietcue-fire-alarm.wav --duration 5
python3 -m uno_q.linux.transport.hub_client \
  /tmp/quietcue-fire-alarm.wav \
  --pc 127.0.0.1:8765 \
  --realtime
```

Open QuietCue on the phone. Within about one second, the dashboard shows the hub,
latest alert, confidence, backend profile, processing latency, and simulated
haptic pattern. The audio-source status only stays green while replay is actively
connected; the last alert remains visible afterward.

The backend profile is currently selected by the hub's `--profile` argument. The
Android profile editor remains local to the phone until profile synchronization is
implemented, so keep the two selections aligned manually during this milestone.

## Replay a real recording

The replay client accepts any uncompressed WAV that is exactly:

- one channel;
- 16 kHz;
- signed 16-bit PCM.

Start the hub with the real YAMNet baseline instead of the simulator:

```bash
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
python -m backend.app.hub_server --classifier yamnet --profile home
```

Then stream the recording with the same `hub_client` command. YAMNet downloads on
first use. Do not interpret demo-tone results or uncalibrated YAMNet scores as
safety validation.
