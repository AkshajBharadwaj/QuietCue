# QuietCue

QuietCue is an AI-assisted accessibility system that turns important environmental
sounds into clear haptic alerts for deaf and hard-of-hearing users.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the system diagram and
current implementation status, and [`docs/DEMO.md`](docs/DEMO.md) for the
3-minute demo runbook.

## Quick start (Windows hub)

One command creates the virtual environment if needed and starts the hub with
the dependency-free demo classifier:

```powershell
.\scripts\run_demo.ps1
```

Useful variants:

```powershell
.\scripts\run_demo.ps1 -Classifier yamnet          # real YAMNet classifier
.\scripts\run_demo.ps1 -SpeechModel tiny.en        # add the gated speech path
.\scripts\run_demo.ps1 -AlertProfile sleep         # start in another profile
.\scripts\run_demo.ps1 -BindHost 0.0.0.0           # accept the Uno Q over LAN/Tailscale
```

Set `QUIETCUE_PAIRING_TOKEN` first when a real Uno Q will connect. On the
board, use `scripts/setup_uno_q.sh` once and `scripts/deploy_uno_q.sh` to
pull and (re)start the microphone client.

## Live Uno Q microphone

The Uno Q can now capture a USB/ALSA microphone continuously, perform lightweight
voice and loudness analysis, and stream 16 kHz mono PCM16 chunks to exactly one
inference hub. The hub has an optional gated Faster-Whisper speech path for
configured names and phrases; it runs in the background so environmental
classification does not wait for transcription.

See [`docs/UNO_Q_MICROPHONE.md`](docs/UNO_Q_MICROPHONE.md) for microphone
detection, level checks, live streaming, local speech-model setup, privacy, and
the current Copilot-versus-Samsung routing boundary.

## Develop without connected hardware

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

The Android companion can also create a reviewable profile draft from a natural-
language situation description and enroll a user-specific sound with three phone-
microphone examples plus background calibration. See
[`docs/PROFILE_AGENT_AND_ENROLLMENT.md`](docs/PROFILE_AGENT_AND_ENROLLMENT.md).

The **My context** tab adds a private, manually controlled identity and context
bank. Users can enroll their name and pronunciation, add people and life context,
and synchronize those approved hints to local speech inference. QuietCue does not
generate or suggest memories from background conversations. See
[`docs/IDENTITY_AND_MEMORY.md`](docs/IDENTITY_AND_MEMORY.md).

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

## Team and submission

- **Team members:** _add names and emails here before submission._
- **License:** [MIT](LICENSE).
- **Setup from scratch:** Quick start above (hub) plus
  [`docs/UNO_Q_MICROPHONE.md`](docs/UNO_Q_MICROPHONE.md) (board) — or use the
  no-hardware demo if no board is available.
- **Demo:** [`docs/DEMO.md`](docs/DEMO.md).
- **Architecture:** [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
- **Benchmarks:** `docs/benchmarks/` (QUAD conversion and profiling reports).
- **Tests:** `python3 -m unittest discover -s tests -v` (no ML dependencies
  needed).

No secrets belong in this repository: pairing tokens, QUAD MCP tokens,
Tailscale keys, and Wi-Fi credentials are environment variables only.
