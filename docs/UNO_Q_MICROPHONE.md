# Uno Q microphone and speech pipeline

QuietCue now supports continuous live capture from an ALSA microphone on the Uno
Q. The live source and WAV replay both emit the same transport contract: mono,
16 kHz, signed 16-bit little-endian PCM in 20–1000 ms chunks.

The connected prototype was detected as:

- USB device: `31b2:0011 DCMT Technology USB Condenser Microphone`
- ALSA card: `Microphone`
- capture endpoint: `plughw:CARD=Microphone,DEV=0`
- native input: mono `S16_LE`, 44.1–192 kHz

`plughw` performs the rate conversion to 16 kHz on the Uno Q. Raw audio is
streamed from `arecord` through a pipe and is never written to disk.

## 1. Check the microphone on the Uno Q

From the repository root on the Uno Q:

```bash
python3 -m uno_q.linux.transport.hub_client --list-microphones
```

Run a three-second, edge-only health check:

```bash
python3 -m uno_q.linux.transport.hub_client \
  --microphone \
  --input-device 'plughw:CARD=Microphone,DEV=0' \
  --max-chunks 6 \
  --compact
```

This prints RMS, peak, and voice-activity metadata. It does not retain the audio.
Speaking near the microphone should raise the level and set `voice=True` on at
least some chunks.

## 2. Start the inference hub

On the Copilot PC or current development computer:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements-speech.txt
```

Start with the dependency-free environmental simulator and the local
Faster-Whisper `tiny.en` speech baseline:

```bash
export QUIETCUE_PAIRING_TOKEN='<development-token>'
python -m backend.app.hub_server \
  --host 0.0.0.0 \
  --classifier demo \
  --profile home \
  --speech-model tiny.en \
  --speech-device cpu \
  --speech-compute-type int8
```

The speech model downloads on first use. Speech windows are buffered in memory
and processed on a background worker. Environmental inference and emergency
alerts do not wait for transcription.

For real environmental classification, also install
`backend/requirements.txt` and replace `--classifier demo` with
`--classifier yamnet`. YAMNet remains a baseline, not a safety-certified model.

Only bind the hub to `0.0.0.0` on a trusted LAN or Tailscale network, and use a
pairing token. The current raw TCP development protocol is not encrypted.

## 3. Stream the microphone to the hub

### Managed runtime (recommended)

Create `~/.quietcue_env` on the Uno Q:

```bash
QUIETCUE_HUB=<copilot-or-development-host>:8765
QUIETCUE_PAIRING_TOKEN=<same-development-token>
QUIETCUE_ALSA_DEVICE=plughw:CARD=Microphone,DEV=0
QUIETCUE_DEVICE_ID=uno-q-dev
```

Then deploy from the repository root on the board:

```bash
./scripts/deploy_uno_q.sh --local
systemctl --user status quietcue-client.service
journalctl --user -u quietcue-client.service -f
```

Deployment synchronizes and flashes the tracked App Lab firmware, then enables
one restartable service for microphone streaming, reconnect, real haptics, and
hardware delivery telemetry. App Lab startup performs health checks only and
does not buzz the motor.

### Foreground diagnostic

On the Uno Q, use the PC's reachable LAN or Tailscale address:

```bash
export QUIETCUE_PAIRING_TOKEN='<same-development-token>'
python3 -m uno_q.linux.transport.hub_client \
  --microphone \
  --input-device 'plughw:CARD=Microphone,DEV=0' \
  --pc '<copilot-or-development-host>:8765' \
  --pairing-token "$QUIETCUE_PAIRING_TOKEN" \
  --phrase 'Akshaj' \
  --chunk-ms 500 \
  --haptics \
  --compact
```

The hub also uses phrase triggers synchronized from the Android active profile,
so `--phrase` is useful for a direct hardware test but is not required once the
profile contains the user's name.

In `auto` routing, the existing selector prefers a reachable Copilot-PC hub and
holds a short lease so audio is sent to exactly one inference target. The Samsung
app currently edits profiles and displays hub state; it is not yet an audio
inference hub, so configure `--pc` for the working hardware path.

## Speech behavior

The speech path remains separate from environmental classification:

1. Uno Q edge analysis identifies likely voice activity.
2. The hub continuously runs the environmental classifier.
3. Voice chunks are buffered for 0.5–4 seconds only in memory.
4. Faster-Whisper transcribes on a background worker.
5. Normalized whole-phrase matching produces `name_called` when a configured
   phrase is present.
6. Profile thresholds, quiet hours, cooldowns, and haptics are applied normally.

The current exact-text phrase match uses a `0.75` attention-confidence baseline
because Whisper's segment log probability is not calibrated to the matched words.
This threshold must be measured against real voices and background speech before
the feature is treated as reliable.

The hub response exposes `speech_pending`, `speech_inference_ms`, and
`speech_error` for health and latency debugging. Do not log or persist transcripts
in production without explicit user consent.
