# QuietCue

QuietCue is an AI-assisted accessibility system that turns important environmental
sounds into clear haptic alerts for deaf and hard-of-hearing users.

## Develop without the Uno Q microphone

The current development loop can replay a validated 16 kHz mono PCM16 WAV through
the same chunked TCP protocol the Uno Q microphone adapter will use later. A
dependency-free demo classifier, backend profile rules, simulated haptic output,
and the Android state feed make the entire software path testable now.

Run a complete terminal-only smoke test:

```bash
python3 scripts/run_no_hardware_demo.py --event fire_alarm --profile home
```

This mode is a deterministic simulator, not a real safety classifier. See
[`docs/NO_HARDWARE_DEMO.md`](docs/NO_HARDWARE_DEMO.md) to keep the server running,
display the alert on an attached Android phone, change profiles, or substitute a
real prerecorded sound for the synthetic fixture.

## First model: environmental sound classification

The first working inference slice uses Google's pretrained YAMNet model. It takes
an uncompressed PCM WAV file, converts it to 16 kHz mono audio, and prints the
highest-confidence AudioSet sound classes.

### Setup

Python 3.13 is supported by the pinned dependencies.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
```

### Run

```bash
python -m backend.inference.sound_classifier path/to/audio.wav
```

The model is downloaded from TensorFlow Hub on the first run and cached locally.
Later runs reuse the cached copy. Use `--top-k 10` to show more predictions.

YAMNet is a baseline classifier, not yet a safety-certified alerting system. Alert
thresholds, temporal smoothing, and emergency-event testing must be added before
its output controls wearable haptics.

## Android companion app

The native Android companion is under [`frontend/android`](frontend/android). Its
first working slice provides persistent built-in and custom profiles, per-sound
alert customization, quiet hours, phrase triggers, and active-profile switching.
See [`frontend/android/README.md`](frontend/android/README.md) for build instructions
and the current integration boundary.

## Backend tests

The transport, WAV source, profile decisions, and full simulated network loop use
the Python standard library and can be tested without installing TensorFlow:

```bash
python3 -m unittest discover -s tests -v
```
